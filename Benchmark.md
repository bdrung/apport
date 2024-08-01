
# Database benchmarks

To run all benchmarks on noble Contents files:

```
./run_all -d
```

To run on jammy Contents files (bigger than noble):

```
./run_all -jd
```

Summary from results on a desktop with a Ryzen 7 5700G:

| DB name              | Creation time | Access time | Memory     | Disk space |
|----------------------|--------------:|------------:|-----------:|-----------:|
| SQLite v1            |      45.374 s |    1.023 ms |    55.5 MB |    1476 MB |
| SQLite v2            |      46.838 s |    1.904 ms |    65.1 MB |    1283 MB |
| SQLite v3            |      50.889 s |    2.264 ms |    79.2 MB |     694 MB |
| SQLite v3b           |      51.354 s |    1.511 ms |    68.9 MB |     797 MB |
| SQLite disqualified1 |      51.307 s |    1.212 ms |    56.5 MB |    1283 MB |
| SQLite disqualified2 |      59.434 s |    1.765 ms |   476.8 MB |     519 MB |
| SQLite disqualified3 |      55.362 s |    1.700 ms |   226.5 MB |     623 MB |
| LevelDB              |      39.455 s |    1.179 ms |  1094.2 MB |     633 MB |
| LMDB                 |      42.013 s |    0.372 ms | 15829.2 MB |    2471 MB |
| NDBM                 |      83.941 s |    0.246 ms |    52.6 MB |    1122 MB |
| GNU DBM              |     121.013 s |    0.164 ms |  1477.8 MB |    1150 MB |
| pickle               |     40.379 s¹ |   0.019 ms² |  1755.4 MB |     774 MB |
| unoptimized pickle   |     61.666 s¹ |   0.020 ms² |  1748.4 MB |     770 MB |

**Legend**:
1. Sum of creation and save duration.
2. Loading the data from disk will take quite some time.

For faster creation speed, check out the
[benchmark rewrite in Rust](https://github.com/bdrung/apport-rs).

## Desktop with a Ryzen 7 5700G

### Creation speed

```
$ ./run_all -jds
$ ./contents_sqlite_v1.py -jds
Creation duration: 45.374 s
Total entries: 8,037,545
Access duration: 1.023 ms
Size: 55.5 MB, RSS: 39.1 MB, Stk: 0.1 MB @ end
Total duration: 45.566 s

$ ./contents_sqlite_v2.py -jds
Creation duration: 46.838 s
Entries in packages table: 72,036
Total entries: 8,037,545
Access duration: 1.904 ms
Size: 65.1 MB, RSS: 48.0 MB, Stk: 0.1 MB @ end
Total duration: 47.019 s

$ ./contents_sqlite_v3.py -jds
Creation duration: 50.889 s
Entries in packages table: 72,036
Entries in directories table: 92,679
Total entries: 8,037,545
Access duration: 2.264 ms
Size: 79.2 MB, RSS: 61.6 MB, Stk: 0.1 MB @ end
Total duration: 51.012 s

$ ./contents_sqlite_v3b.py -jds
Creation duration: 51.354 s
Entries in packages table: 72,036
Entries in directories table: 30,219
Total entries: 8,037,545
Access duration: 1.511 ms
Size: 68.9 MB, RSS: 51.6 MB, Stk: 0.1 MB @ end
Total duration: 51.493 s

$ ./contents_sqlite_disqualified1.py -jds
Creation duration: 51.307 s
Total entries: 8,037,545
Access duration: 1.212 ms
Size: 56.5 MB, RSS: 39.1 MB, Stk: 0.1 MB @ end
Total duration: 51.490 s

$ ./contents_sqlite_disqualified2.py -jds
Creation duration: 59.434 s
Entries in packages table: 72,036
Entries in directories table: 1,007,439
Entries in names table: 1,758,472
Total entries: 8,037,545
Access duration: 1.765 ms
Size: 476.8 MB, RSS: 459.8 MB, Stk: 0.1 MB @ end
Total duration: 59.593 s

$ ./contents_sqlite_disqualified3.py -jds
Creation duration: 55.362 s
Entries in packages table: 72,036
Entries in directories table: 1,007,439
Total entries: 8,037,544
Access duration: 1.700 ms
Size: 226.5 MB, RSS: 209.8 MB, Stk: 0.1 MB @ end
Total duration: 55.495 s

$ ./contents_leveldb.py -jds
Creation duration: 39.455 s
Total entries: 8,037,545
Access duration: 1.179 ms
Size: 1094.2 MB, RSS: 1023.7 MB, Stk: 0.1 MB @ end
Total duration: 1 min 2.321 s (= 62.321 s)

$ ./contents_lmdb.py -jds
Creation duration: 42.013 s
Total entries: 8,037,545
Access duration: 0.372 ms
Size: 15829.2 MB, RSS: 1695.5 MB, Stk: 0.1 MB @ end
Total duration: 42.069 s

$ ./contents_ndbm.py -jds
Creation duration: 1 min 23.941 s (= 83.941 s)
Total entries: 8,037,545
Access duration: 0.246 ms
Size: 52.6 MB, RSS: 35.9 MB, Stk: 0.1 MB @ end
Total duration: 1 min 25.946 s (= 85.946 s)

$ ./contents_dbm.py -jds
Creation duration: 2 min 1.013 s (= 121.013 s)
Total entries: 8,037,545
Access duration: 0.164 ms
Size: 1477.8 MB, RSS: 641.5 MB, Stk: 0.1 MB @ end
Total duration: 2 min 1.067 s (= 121.067 s)

$ ./contents_pickle.py -jds
Creation duration: 36.160 s
Save duration: 4.219 s
Total entries: 8,037,545
Access duration: 0.019 ms
Size: 1755.4 MB, RSS: 1739.1 MB, Stk: 0.1 MB @ end
Total duration: 40.619 s

$ ./contents_unoptimized_pickle.py -jds
Creation duration: 57.485 s
Save duration: 4.181 s
Total entries: 7,996,187
Access duration: 0.020 ms
Size: 1748.4 MB, RSS: 1732.2 MB, Stk: 0.1 MB @ end
Total duration: 1 min 1.896 s (= 61.896 s)
```

### Disk consumption

```
$ du -B M -s contents_cache/*jammy-amd* | grep -v lock | sort -n
519M	contents_cache/contents_mapping-jammy-amd64_disqualified2.sqlite3
623M	contents_cache/contents_mapping-jammy-amd64_disqualified3.sqlite3
633M	contents_cache/contents_mapping-jammy-amd64.leveldb
694M	contents_cache/contents_mapping-jammy-amd64_v3.sqlite3
770M	contents_cache/contents_mapping-jammy-amd64.pickle_old
774M	contents_cache/contents_mapping-jammy-amd64.pickle
797M	contents_cache/contents_mapping-jammy-amd64_v3b.sqlite3
1122M	contents_cache/contents_mapping-jammy-amd64.ndbm.db
1150M	contents_cache/contents_mapping-jammy-amd64.dbm
1283M	contents_cache/contents_mapping-jammy-amd64_disqualified1.sqlite3
1283M	contents_cache/contents_mapping-jammy-amd64_v2.sqlite3
1476M	contents_cache/contents_mapping-jammy-amd64_v1.sqlite3
2471M	contents_cache/contents_mapping-jammy-amd64.lmdb
```

## Raspbery Pi Zero 2W

Results on a Raspberry Pi Zero 2W on 2024-07-31 with jammy Contents
(dbm and ndbm were too slow):

```
$ ./run_all -dsj
$ ./contents_sqlite_v1.py -dsj
Creation duration: 14 min 43.170 s (= 883.170 s)
Total entries: 8,037,545
Access duration: 52.820 ms
Total duration: 16 min 14.203 s (= 974.203 s)

$ ./contents_sqlite_v2.py -dsj
Creation duration: 15 min 7.583 s (= 907.583 s)
Entries in packages table: 72,036
Total entries: 8,037,545
Access duration: 38.480 ms
Total duration: 16 min 20.018 s (= 980.018 s)

$ ./contents_sqlite_v3.py -dsj
Creation duration: 16 min 16.836 s (= 976.836 s)
Entries in packages table: 72,036
Entries in directories table: 92,679
Total entries: 8,037,545
Access duration: 47.185 ms
Total duration: 16 min 57.041 s (= 1017.041 s)

$ ./contents_sqlite_v3b.py -dsj
Creation duration: 16 min 27.433 s (= 987.433 s)
Entries in packages table: 72,036
Entries in directories table: 30,219
Total entries: 8,037,545
Access duration: 47.576 ms
Total duration: 17 min 18.059 s (= 1038.059 s)

$ ./contents_leveldb.py -dsj
Creation duration: 28 min 53.844 s (= 1733.844 s)
Total entries: 8,037,545
Access duration: 144.482 ms
Total duration: 32 min 53.198 s (= 1973.198 s)

$ ./contents_lmdb.py -dsj
Creation duration: 35 min 9.227 s (= 2109.227 s)
Total entries: 8,037,545
Access duration: 113.656 ms
Total duration: 36 min 35.423 s (= 2195.423 s)

$ ./contents_pickle.py -dsj
Creation duration: 24 min 36.127 s (= 1476.127 s)
Save duration: 4 h 9 min 1.947 s (= 14941.947 s)
Total entries: 7,911,114
Access duration: 33.207 ms
Total duration: 4 h 37 min 24.957 s (= 16644.957 s)
```

Results on a Raspberry Pi Zero 2W on 2024-07-31 with noble Contents
(dbm and ndbm were too slow):

```
$ ./run_all -ds
$ ./contents_sqlite_v1.py -ds
Creation duration: 4 min 45.552 s (= 285.552 s)
Total entries: 4,333,447
Access duration: 36.293 ms
Total duration: 5 min 21.796 s (= 321.796 s)

$ ./contents_sqlite_v2.py -ds
Creation duration: 4 min 57.238 s (= 297.238 s)
Entries in packages table: 66,602
Total entries: 4,333,447
Access duration: 40.230 ms
Total duration: 5 min 31.144 s (= 331.144 s)

$ ./contents_sqlite_v3.py -ds
Creation duration: 5 min 30.401 s (= 330.401 s)
Entries in packages table: 66,602
Entries in directories table: 79,371
Total entries: 4,333,447
Access duration: 45.070 ms
Total duration: 5 min 51.020 s (= 351.020 s)

$ ./contents_sqlite_v3b.py -ds
Creation duration: 5 min 27.268 s (= 327.268 s)
Entries in packages table: 66,602
Entries in directories table: 26,298
Total entries: 4,333,447
Access duration: 47.796 ms
Total duration: 5 min 51.213 s (= 351.213 s)

$ ./contents_leveldb.py -ds
Creation duration: 8 min 19.833 s (= 499.833 s)
Total entries: 4,333,447
Access duration: 367.406 ms
Total duration: 8 min 54.908 s (= 534.908 s)

$ ./contents_lmdb.py -ds
Creation duration: 10 min 9.856 s (= 609.856 s)
Total entries: 4,333,447
Access duration: 50.292 ms
Total duration: 11 min 52.888 s (= 712.888 s)

$ ./contents_pickle.py -ds
Creation duration: 3 min 47.371 s (= 227.371 s)
Save duration: 46 min 9.992 s (= 2769.992 s)
Total entries: 4,333,447
Access duration: 17.507 ms
Total duration: 51 min 20.201 s (= 3080.201 s)
```

### Swap disabled

Results on a Raspberry Pi Zero 2W with swap disabled:

```
$ ./run_all -dsj
$ ./contents_sqlite_v1.py -dsj
Creation duration: 14 min 42.957 s (= 882.957 s)
Total entries: 8,037,545
Access duration: 36.858 ms
Total duration: 16 min 11.612 s (= 971.612 s)

$ ./contents_sqlite_v2.py -dsj
Creation duration: 15 min 2.569 s (= 902.569 s)
Entries in packages table: 72,036
Total entries: 8,037,545
Access duration: 38.994 ms
Total duration: 16 min 12.557 s (= 972.557 s)

$ ./contents_sqlite_v3.py -dsj
Creation duration: 16 min 26.629 s (= 986.629 s)
Entries in packages table: 72,036
Entries in directories table: 92,679
Total entries: 8,037,545
Access duration: 51.080 ms
Total duration: 17 min 6.754 s (= 1026.754 s)

$ ./contents_leveldb.py -dsj
Killed
./contents_leveldb.py failed with 137

$ ./contents_lmdb.py -dsj
Killed
./contents_lmdb.py failed with 137

$ ./contents_ndbm.py -dsj  # never ending

$ ./contents_pickle.py
Killed
./contents_pickle.py failed with 137

$ ./contents_unoptimized_pickle.py
Killed
./contents_unoptimized_pickle.py failed with 137
```
