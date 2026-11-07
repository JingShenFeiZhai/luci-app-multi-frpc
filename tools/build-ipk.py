#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build luci-app-multi-frpc ipk packages without the OpenWrt SDK.

The produced files follow the same layout as OpenWrt's ``ipkg-build`` /
``luci.mk`` output:

    outer tar.gz
      ./debian-binary      ("2.0\\n")
      ./data.tar.gz        (luasrc -> /usr/lib/lua/luci, root -> /)
      ./control.tar.gz     (control, conffiles, postinst, postinst-pkg, prerm)

Usage:
    python3 tools/build-ipk.py [--version 1.0.2] [--release 1]
                               [--output dist] [--no-i18n]

The script reads PKG_VERSION / PKG_RELEASE from the Makefile by default.
"""

import argparse
import gzip
import io
import os
import re
import struct
import sys
import tarfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LUCI_LIB = "usr/lib/lua/luci"
CONFIG_FILE = "etc/config/multi-frpc"
I18N_LANG = "zh-cn"


# ---------------------------------------------------------------------------
# Makefile helpers
# ---------------------------------------------------------------------------

def makefile_var(name, default=None):
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^%s\s*[:?]?=\s*(.+)$" % re.escape(name), text, re.M)
    return match.group(1).strip() if match else default


# ---------------------------------------------------------------------------
# tar.gz helpers
# ---------------------------------------------------------------------------

def _add(tar, name, data, mode, mtime):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    info.mtime = mtime
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    tar.addfile(info, io.BytesIO(data))


def gzip_bytes(data, mtime=0):
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=mtime) as gz:
        gz.write(data)
    return buf.getvalue()


def tar_bytes(entries):
    """entries: list of (name, data-or-None, mode). None data means directory."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for name, data, mode in entries:
            if data is None:
                info = tarfile.TarInfo(name)
                info.type = tarfile.DIRTYPE
                info.mode = mode
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                tar.addfile(info)
            else:
                _add(tar, name, data, mode, 0)
    return buf.getvalue()


def file_mode(arcname):
    if arcname.startswith("etc/init.d/") or arcname.startswith("etc/uci-defaults/"):
        return 0o755
    return 0o644


def collect_tree(mappings):
    """mappings: [(source dir, destination prefix)] -> {arcname: bytes} with dirs."""
    entries = {}
    for src, dest in mappings:
        if not src.is_dir():
            raise SystemExit("missing source directory: %s" % src)
        for path in sorted(src.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(src).as_posix()
            arc = ("%s/%s" % (dest, rel)).lstrip("/") if dest else rel
            entries[arc] = path.read_bytes()
    return entries


def tree_entries(files):
    """Expand a {path: data} mapping into tar entries incl. parent directories."""
    dirs = set()
    for arc in files:
        parent = arc.rsplit("/", 1)[0] if "/" in arc else ""
        while parent:
            dirs.add(parent)
            parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
    entries = [("./" + d, None, 0o755) for d in sorted(dirs)]
    entries += [("./" + arc, data, file_mode(arc)) for arc, data in sorted(files.items())]
    return entries


def check_ipk(path, expected):
    """Re-open a produced ipk and make sure the container is valid."""
    with tarfile.open(path, "r:gz") as outer:
        names = set(outer.getnames())
        for required in ("./debian-binary", "./data.tar.gz", "./control.tar.gz"):
            if required not in names:
                raise SystemExit("%s: missing %s" % (path, required))
        control = tarfile.open(fileobj=outer.extractfile("./control.tar.gz"),
                              mode="r:gz")
        text = control.extractfile("./control").read().decode("utf-8")
        for field in ("Package:", "Version:", "Architecture: all"):
            if field not in text:
                raise SystemExit("%s: broken control file" % path)
        data = tarfile.open(fileobj=outer.extractfile("./data.tar.gz"),
                            mode="r:gz")
        packaged = {"./" + m.name.lstrip("./") for m in data.getmembers() if m.isfile()}
    missing = {"./" + name for name in expected} - packaged
    if missing:
        raise SystemExit("%s: missing files: %s" % (path, sorted(missing)))


def build_ipk(control_tar, data_tar):
    """Assemble the outer tar.gz container used by opkg/OpenWrt."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tar:
        _add(tar, "./debian-binary", b"2.0\n", 0o644, 0)
        _add(tar, "./data.tar.gz", gzip_bytes(data_tar), 0o644, 0)
        _add(tar, "./control.tar.gz", gzip_bytes(control_tar), 0o644, 0)
    return gzip_bytes(buf.getvalue())


# ---------------------------------------------------------------------------
# control files
# ---------------------------------------------------------------------------

POSTINST = """#!/bin/sh
[ "${IPKG_NO_SCRIPT}" = "1" ] && exit 0
[ -s ${IPKG_INSTROOT}/lib/functions.sh ] || exit 0
. ${IPKG_INSTROOT}/lib/functions.sh
default_postinst $0 $@
"""

PRERM = """#!/bin/sh
[ -s ${IPKG_INSTROOT}/lib/functions.sh ] || exit 0
. ${IPKG_INSTROOT}/lib/functions.sh
default_prerm $0 $@
"""


def postinst_pkg(script):
    return """[ -n "${IPKG_INSTROOT}" ] || {
\t(. /etc/uci-defaults/%s) && rm -f /etc/uci-defaults/%s
\texit 0
}
""" % (script, script)


def control_tar(control, conffiles, uci_script):
    entries = [
        ("./control", control.encode("utf-8"), 0o644),
        ("./postinst", POSTINST.encode("utf-8"), 0o755),
        ("./postinst-pkg", postinst_pkg(uci_script).encode("utf-8"), 0o755),
        ("./prerm", PRERM.encode("utf-8"), 0o755),
    ]
    if conffiles:
        entries.insert(1, ("./conffiles",
                           ("\n".join(conffiles) + "\n").encode("utf-8"), 0o644))
    return tar_bytes(entries)


def control_text(name, version, depends, title, size, epoch, source=None):
    source = source or name
    return """Package: %s
Version: %s
Depends: %s
Source: package/%s
SourceName: %s
Section: luci
SourceDateEpoch: %d
Architecture: all
Installed-Size: %d
Description:  %s
""" % (name, version, depends, source, name, epoch, size, title)


# ---------------------------------------------------------------------------
# i18n: po -> lmo (same binary format as luci's po2lmo)
# ---------------------------------------------------------------------------

def _u32(value):
    return value & 0xFFFFFFFF


def _get16(data, off):
    return data[off] | (data[off + 1] << 8)


def sfh_hash(data):
    """Paul Hsieh's hash, as used by luci's template_lmo.c."""
    length = len(data)
    if length <= 0:
        return 0
    h = length
    rem = length & 3
    i = 0
    for _ in range(length >> 2):
        h = _u32(h + _get16(data, i))
        tmp = _u32((_get16(data, i + 2) << 11) ^ h)
        h = _u32((h << 16) ^ tmp)
        i += 4
        h = _u32(h + (h >> 11))
    if rem == 3:
        h = _u32(h + _get16(data, i))
        h = _u32(h ^ (h << 16))
        ch = data[i + 2]
        if ch >= 128:
            ch -= 256
        h = _u32(h ^ _u32(ch << 18))
        h = _u32(h + (h >> 11))
    elif rem == 2:
        h = _u32(h + _get16(data, i))
        h = _u32(h ^ (h << 11))
        h = _u32(h + (h >> 17))
    elif rem == 1:
        ch = data[i]
        if ch >= 128:
            ch -= 256
        h = _u32(h + ch)
        h = _u32(h ^ (h << 10))
        h = _u32(h + (h >> 1))
    h = _u32(h ^ (h << 3))
    h = _u32(h + (h >> 5))
    h = _u32(h ^ (h << 4))
    h = _u32(h + (h >> 17))
    h = _u32(h ^ (h << 25))
    h = _u32(h + (h >> 6))
    return h


def _canon(text):
    """Whitespace normalisation done by lmo_canon_hash()."""
    out = []
    prev = " "
    for ch in text:
        if ch.isspace():
            if not prev.isspace():
                out.append(" ")
        else:
            out.append(ch)
        prev = ch
    result = "".join(out)
    if result and result[-1].isspace():
        result = result[:-1]
    return result.encode("utf-8")


def key_hash(msgid):
    return sfh_hash(_canon(msgid))


_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\",
    "a": "\a", "b": "\b", "f": "\f", "v": "\v",
}


def _unescape(text):
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            out.append(_ESCAPES.get(text[i + 1], text[i + 1]))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_po(path):
    entries = []
    msgid = None
    msgstr = None
    mode = None
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\r\n")
            if not line.strip() or line.startswith("#"):
                continue
            if line.startswith("msgctxt"):
                raise SystemExit("%s: msgctxt is not supported" % path)
            if line.startswith("msgid_plural"):
                raise SystemExit("%s: plural forms are not supported" % path)
            if line.startswith("msgid "):
                if msgid is not None:
                    entries.append((msgid, msgstr or ""))
                msgid = _unescape(line[6:].strip()[1:-1])
                msgstr = ""
                mode = "id"
            elif line.startswith("msgstr "):
                msgstr = _unescape(line[7:].strip()[1:-1])
                mode = "str"
            elif line.startswith('"'):
                part = _unescape(line.strip()[1:-1])
                if mode == "id":
                    msgid += part
                else:
                    msgstr += part
            else:
                raise SystemExit("%s: cannot parse line: %s" % (path, line))
    if msgid is not None:
        entries.append((msgid, msgstr or ""))
    return [(i, s) for i, s in entries if i != ""]


def po2lmo(po_path):
    """Compile a .po file into the binary .lmo format used by LuCI."""
    data = bytearray()
    records = []
    for msgid, msgstr in parse_po(po_path):
        value = msgstr.encode("utf-8")
        offset = len(data)
        data += value
        while len(data) % 4:
            data.append(0)
        records.append((key_hash(msgid), sfh_hash(value), offset, len(value)))

    records.sort(key=lambda item: item[0])
    index_offset = len(data)
    out = bytearray(data)
    for record in records:
        out += struct.pack(">IIII", *record)
    out += struct.pack(">I", index_offset)
    return bytes(out), len(records)


# ---------------------------------------------------------------------------
# packaging
# ---------------------------------------------------------------------------

def build(args):
    version = args.version or makefile_var("PKG_VERSION", "1.0.2")
    release = args.release or makefile_var("PKG_RELEASE", "1")
    title = makefile_var("LUCI_TITLE", "LuCI support for FRPC (multiple frps servers)")
    full_version = "%s-%s" % (version, release)
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", time.time()))
    outdir = Path(args.output)
    if not outdir.is_absolute():
        outdir = REPO / outdir
    outdir.mkdir(parents=True, exist_ok=True)

    # ---- main package -----------------------------------------------------
    files = collect_tree([
        (REPO / "luasrc", LUCI_LIB),
        (REPO / "root", ""),
    ])
    main_name = "luci-app-multi-frpc"
    data_tar = tar_bytes(tree_entries(files))
    data_gz = gzip_bytes(data_tar)
    control = control_text(main_name, full_version, "libc, wget, frpc", title,
                           len(data_gz), epoch)
    control_tar_data = control_tar(control, ["/" + CONFIG_FILE],
                                   "luci-multi-frpc")
    ipk = build_ipk(control_tar_data, data_tar)
    main_path = outdir / ("%s_%s_all.ipk" % (main_name, full_version))
    main_path.write_bytes(ipk)
    check_ipk(main_path, set(files))
    print("built %s (%d bytes, %d files)" % (main_path, len(ipk), len(files)))

    # ---- optional translation package -------------------------------------
    if not args.no_i18n:
        po_files = sorted((REPO / "po" / I18N_LANG).glob("*.po"))
        if po_files:
            i18n_files = {}
            for po in po_files:
                lmo, count = po2lmo(po)
                arc = "%s/i18n/%s.%s.lmo" % (LUCI_LIB, po.stem, I18N_LANG)
                i18n_files[arc] = lmo
                print("  compiled %s -> %s (%d entries)" % (po.name, arc, count))

            uci_name = "luci-i18n-multi-frpc-%s" % I18N_LANG
            i18n_files["etc/uci-defaults/" + uci_name] = (
                "uci set luci.languages.%s='简体中文 (Simplified Chinese)'; uci commit luci\n"
                % I18N_LANG.replace("-", "_")
            ).encode("utf-8")

            i18n_data_tar = tar_bytes(tree_entries(i18n_files))
            i18n_data_gz = gzip_bytes(i18n_data_tar)
            i18n_control = control_text(
                uci_name, full_version, "libc, " + main_name,
                "Translation for %s - 简体中文 (Simplified Chinese)" % main_name,
                len(i18n_data_gz), epoch, source=main_name)
            i18n_ipk = build_ipk(
                control_tar(i18n_control, [], uci_name), i18n_data_tar)
            i18n_path = outdir / ("%s_%s_all.ipk" % (uci_name, full_version))
            i18n_path.write_bytes(i18n_ipk)
            check_ipk(i18n_path, set(i18n_files))
            print("built %s (%d bytes)" % (i18n_path, len(i18n_ipk)))

    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", help="package version (default: Makefile)")
    parser.add_argument("--release", help="package release (default: Makefile)")
    parser.add_argument("--output", default="dist", help="output directory (default: dist)")
    parser.add_argument("--no-i18n", action="store_true", help="skip the zh-cn translation package")
    return build(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
