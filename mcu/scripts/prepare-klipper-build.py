#!/usr/bin/env python
from __future__ import print_function

import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
import time


EXCLUDED_DIRS = set([".git", ".jj", "out", "__pycache__"])


def fail(message):
    print(message, file=sys.stderr)
    return 1


def info(message):
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def remove_path(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)


def copy_file(src, dst):
    ensure_dir(os.path.dirname(dst))
    remove_path(dst)
    if os.path.islink(src):
        os.symlink(os.readlink(src), dst)
    else:
        shutil.copy2(src, dst)
        # Ensure make notices content updates even if source mtimes came from a checkout.
        now = time.time()
        os.utime(dst, (now, now))


def copy_file_if_different(src, dst):
    if os.path.islink(src):
        if os.path.islink(dst) and os.readlink(src) == os.readlink(dst):
            return False
        copy_file(src, dst)
        return True

    if os.path.exists(dst) and not os.path.islink(dst):
        try:
            if filecmp.cmp(src, dst, shallow=False):
                return False
        except OSError:
            pass

    copy_file(src, dst)
    return True


def iter_files(root, excluded_dirs=None):
    excluded_dirs = excluded_dirs or set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames
            if name not in excluded_dirs
        ]
        for filename in sorted(filenames):
            src_path = os.path.join(dirpath, filename)
            relpath = os.path.relpath(src_path, root)
            yield relpath, src_path


def iter_git_files(root):
    try:
        output = subprocess.check_output(
            ["git", "-C", root, "ls-files", "-z"]
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    if not isinstance(output, str):
        output = output.decode("utf-8")

    files = []
    for relpath in output.split("\0"):
        if relpath:
            files.append((relpath, os.path.join(root, relpath)))
    return files


def is_protected(relpath, protected):
    for item in protected:
        if relpath == item or relpath.startswith(item + os.sep):
            return True
    return False


def sync_files(src_root, dst_root, excluded_dirs=None, skip_files=None,
               use_gitignore=False, delete_stale=False, protected=None):
    skip_files = skip_files or set()
    protected = protected or set()
    changed = []
    source_files = set()

    files = iter_git_files(src_root) if use_gitignore else None
    if files is None:
        files = list(iter_files(src_root, excluded_dirs))

    for relpath, src_path in files:
        source_files.add(relpath)
        if relpath in skip_files:
            continue
        dst_path = os.path.join(dst_root, relpath)
        if copy_file_if_different(src_path, dst_path):
            changed.append(relpath)

    if delete_stale:
        for relpath, dst_path in list(iter_files(dst_root)):
            if relpath in source_files or relpath in skip_files:
                continue
            if is_protected(relpath, protected):
                continue
            remove_path(dst_path)
            changed.append(relpath)

    return changed


def parse_patch_targets(patch_path):
    targets = []
    with open(patch_path, "r") as f:
        for line in f:
            if not line.startswith("+++ "):
                continue
            path = line.split(None, 1)[1].split("\t", 1)[0].strip()
            if path == "/dev/null":
                continue
            if path.startswith("b/"):
                path = path[2:]
            targets.append(path)
    return sorted(set(targets))


def apply_patch(work_dir, patch_path):
    with open(patch_path, "rb") as patch_file:
        subprocess.check_call(
            ["patch", "-s", "-p1", "-N", "-r", "-"],
            cwd=work_dir,
            stdin=patch_file,
        )


def sync_patched_files(klipper_src, build_dir, patch_path, patch_targets):
    if not patch_targets:
        return []

    tmp_dir = tempfile.mkdtemp(prefix="indx-klipper-patch-")
    try:
        for relpath in patch_targets:
            src_path = os.path.join(klipper_src, relpath)
            if os.path.exists(src_path):
                copy_file(src_path, os.path.join(tmp_dir, relpath))

        apply_patch(tmp_dir, patch_path)

        changed = []
        for relpath in patch_targets:
            expected_path = os.path.join(tmp_dir, relpath)
            if not os.path.exists(expected_path):
                continue
            dst_path = os.path.join(build_dir, relpath)
            if copy_file_if_different(expected_path, dst_path):
                changed.append(relpath)
        return changed
    finally:
        shutil.rmtree(tmp_dir)


def remove_stale_autoconf(build_dir):
    config_path = os.path.join(build_dir, ".config")
    autoconf_path = os.path.join(build_dir, "out", "autoconf.h")
    if (
        os.path.exists(config_path)
        and os.path.exists(autoconf_path)
        and os.path.getmtime(config_path) > os.path.getmtime(autoconf_path)
    ):
        os.remove(autoconf_path)


def normalized_config(build_dir, seed_config):
    fd, config_path = tempfile.mkstemp(prefix="indx-klipper-config-")
    os.close(fd)
    shutil.copy2(seed_config, config_path)
    env = os.environ.copy()
    env["KCONFIG_CONFIG"] = config_path
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    devnull = open(os.devnull, "wb")
    try:
        subprocess.check_call(
            [sys.executable, "lib/kconfiglib/olddefconfig.py", "src/Kconfig"],
            cwd=build_dir,
            env=env,
            stdout=devnull,
            stderr=devnull,
        )
    finally:
        devnull.close()
    return config_path


def main(argv):
    if len(argv) != 4:
        return fail("usage: %s <klipper-src> <build-dir> <config>" % argv[0])

    script_path = os.path.abspath(argv[0])
    mcu_root = os.path.abspath(os.path.join(os.path.dirname(script_path), ".."))
    klipper_src = os.path.abspath(argv[1])
    build_dir = os.path.abspath(argv[2])
    config_path = os.path.abspath(os.path.join(mcu_root, argv[3]))
    patch_path = os.path.join(mcu_root, "patches", "klipper-indx.patch")

    if not os.path.isfile(os.path.join(klipper_src, "Makefile")):
        return fail("Klipper source not found at %s" % klipper_src)
    if not os.path.isfile(config_path):
        return fail("INDX config not found at %s" % config_path)

    ensure_dir(build_dir)

    patch_targets = parse_patch_targets(patch_path)
    changed = []

    klipper_skip = set(patch_targets)
    klipper_skip.add(".config")
    klipper_skip.add(".config.old")
    klipper_protected = set([
        ".config",
        ".config.old",
        "out",
        "src/indx",
    ])

    changed.extend(sync_files(
        klipper_src,
        build_dir,
        excluded_dirs=EXCLUDED_DIRS,
        skip_files=klipper_skip,
        use_gitignore=True,
        delete_stale=True,
        protected=klipper_protected,
    ))
    changed.extend(sync_patched_files(
        klipper_src, build_dir, patch_path, patch_targets))
    changed.extend([
        os.path.join("src", "indx", relpath)
        for relpath in sync_files(
            os.path.join(mcu_root, "src"),
            os.path.join(build_dir, "src", "indx"),
        )
    ])

    generated_config = normalized_config(build_dir, config_path)
    try:
        if copy_file_if_different(generated_config, os.path.join(build_dir, ".config")):
            changed.append(".config")
    finally:
        remove_path(generated_config)

    old_state = os.path.join(build_dir, ".indx-sync-state.json")
    if os.path.exists(old_state):
        os.remove(old_state)
    remove_stale_autoconf(build_dir)

    if changed:
        info("Updated INDX Klipper build tree: %d file(s)" % len(changed))
    else:
        info("INDX Klipper build tree is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
