#!/bin/sh
set -eu

klipper_dir=${1:-"${HOME}/klipper"}
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ ! -d "$klipper_dir" ]; then
    echo "Klipper directory does not exist: $klipper_dir" >&2
    exit 1
fi

extras_dir="$klipper_dir/klippy/extras"
indx_link="$extras_dir/indx"
exclude_file="$klipper_dir/.git/info/exclude"

if [ -L "$indx_link" ]; then
    rm "$indx_link"
elif [ -e "$indx_link" ]; then
    echo "Refusing to replace non-symlink: $indx_link" >&2
    exit 1
fi

ln -s "$repo_dir/host" "$indx_link"

if ! grep -qxF "klippy/extras/indx" "$exclude_file"; then
    printf '%s\n' "klippy/extras/indx" >> "$exclude_file"
fi

mkdir -p "$repo_dir/out"
if [ -L "$repo_dir/out/klipper" ]; then
    rm "$repo_dir/out/klipper"
elif [ -e "$repo_dir/out/klipper" ]; then
    echo "Refusing to replace non-symlink: $repo_dir/out/klipper" >&2
    exit 1
fi

ln -s "$klipper_dir" "$repo_dir/out/klipper"

echo "Installed INDX Klipper links for: $klipper_dir"
echo "Build MCU firmware with: make"
echo "Flash MCU firmware with: make flash FLASH_DEVICE=/dev/serial/by-id/..."
