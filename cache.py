#!/usr/bin/python3

import argparse
import timeit
import subprocess

import apt


def get_map(cache):
    file_map = {}
    for package in cache:
        if not package.is_installed:
            continue
        for _file in package.installed_files:
            file_map[_file] = package.name
    return file_map
    # return {p.name: p.installed_files for p in cache if p.is_installed}


def test_speed_cache():
    cache = apt.Cache()
    file_map = get_map(cache)
    curl = file_map["/usr/lib/x86_64-linux-gnu/libcurl.so.4"]
    lv2 = file_map["/usr/lib/lv2/ui.lv2/ui.h"]
    nss_nis = file_map["/lib/i386-linux-gnu/libnss_nis.so.2.0.0"]
    curl = file_map["/usr/lib/x86_64-linux-gnu/libcurl.so.4"]
    lv2 = file_map["/usr/lib/lv2/ui.lv2/ui.h"]
    nss_nis = file_map["/lib/i386-linux-gnu/libnss_nis.so.2.0.0"]
    return curl, lv2, nss_nis


def dpkg_query_S(filename):
    dpkg_query = subprocess.run(["dpkg-query", "-S", filename], stdout=subprocess.PIPE, text=True)
    lines = dpkg_query.stdout.strip().split("\n")
    if not lines:
        return None
    for line in lines:
        packages, filename = line.rsplit(":", maxsplit=1)
    return packages.strip()


def test_speed_dpkg():
    curl = dpkg_query_S("/usr/lib/x86_64-linux-gnu/libcurl.so.4")
    lv2 = dpkg_query_S("/usr/lib/lv2/ui.lv2/ui.h")
    nss_nis = dpkg_query_S("/lib/i386-linux-gnu/libnss_nis.so.2.0.0")
    curl = dpkg_query_S("/usr/lib/x86_64-linux-gnu/libcurl.so.4")
    lv2 = dpkg_query_S("/usr/lib/lv2/ui.lv2/ui.h")
    nss_nis = dpkg_query_S("/lib/i386-linux-gnu/libnss_nis.so.2.0.0")
    return curl, lv2, nss_nis


def test_speed():
    print(f"apt.Cache time: {timeit.timeit(test_speed_cache, number=1)}")
    print(f"dpkg -S time: {timeit.timeit(test_speed_dpkg, number=1)}")
    cache = apt.Cache()
    file_map = get_map(cache)
    print(f"dict lookup 1000x: {timeit.timeit(lambda: file_map['/lib/i386-linux-gnu/libnss_nis.so.2.0.0'], number=1000)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", nargs="*")
    parser.add_argument("-t", action="store_true", help="test speed")
    parser.add_argument("-o", "--output", default="/tmpfs/package_map.list")
    args = parser.parse_args()

    if args.t:
        test_speed()
        return

    cache = apt.Cache()
    file_map = get_map(cache)
    with open(args.output, "w", encoding="utf-8") as output_file:
        for file, package in sorted(file_map.items()):
            output_file.write(f"{file}: {package}\n")

    # print(file_map.keys())
    for filename in args.filename:
        if filename in file_map:
            print(f"{file_map[filename]}: {args.filename}")


if __name__ == "__main__":
    main()
