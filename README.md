# s3v
Convinient CLI tool to work with versioned S3 buckets. Like `aws s3` or `aws s3api` but much easier to use.

s3v is like if `aws s3` and `aws s3api` were built on our planet — for actual humans.

## Installation
~~~
# recommended
pipx install s3v

# or from git
pipx install git+https://github.com/yaroslaff/s3v
~~~

## Configuration
s3v uses boto3, so configuration is same as for `aws` utility (same `~/.aws/` files or `AWS_` shell variables, and optional `--profile NAME` argument)

## Examples
We upload three versions of same file, each one will overwrite old copy. 


### Upload

```bash
$ echo 1 > test.txt 
$ s3v cp test.txt s3://stg-objectlock/s3v/
$ echo 2 > test.txt 
$ s3v cp test.txt s3://stg-objectlock/s3v/
$ echo 3 > test.txt 
$ s3v cp test.txt s3://stg-objectlock/s3v/
```
You can also give full target name like s3://stg-objectlock/s3v/test.txt. `s3://` prefix is optional (s3 will try to guess what is local file and what is bucket name).


### List
Now, list contents of s3v logical 'folder' (all objects with name starting with `s3v/`). In "ls" we see filename, last modification time (UTC), size of latest copy and number of versions in storage. If we give full name of object, ls will list all versions of this object.

```bash
$ s3v ls stg-objectlock/s3v
test.txt                                |2026-02-10 16:21:55|              2|   3|

$ s3v ls stg-objectlock/s3v/test.txt
Objects under prefix 's3v/test.txt':
s3v/test.txt
   by0fQCa9Jl7gFgl8vKEjaDvl8z3CSRnD          2  2026-02-10 16:21:30
   LHK6nA8Ny5YHNh7TOoH94LDinqCH9Czt          2  2026-02-10 16:21:46
   iIGXCsBmEKvBq7DhaP09DIzp3fLO9d1H          2  2026-02-10 16:21:55
```


### Downloading

`s3v cp` will download latest version of file.
```bash
$ s3v cp stg-objectlock/s3v/test.txt .

$ cat test.txt 
3
```

Give `-s VERSION` to download specific version.

```bash
$ s3v cp stg-objectlock/s3v/test.txt . -s by0fQCa9Jl7gFgl8vKEjaDvl8z3CSRnD
  Using version: by0fQCa9Jl7gFgl8vKEjaDvl8z3CSRnD
$ cat test.txt 
1
```

You can use human language for `-s`, it understands words: first (oldest), latest, (last, newest), previous (prev, p). 
Numerical index where 0 is oldest copy, 1 is next one and so on. Negative numbers are counted from latest, e.g. -1 is latest copy, -2 is little older and so on.
You can give time specification (we use [dateparser](https://dateparser.readthedocs.io/en/latest/)) so it understands "yesterday", "2 weeks ago" or "2026-02-10 16:22" or "16:22". If time specification given, s3v will download version which was current on that time (latest uploaded before this time). 

```
$ s3v cp stg-objectlock/s3v/test.txt . -s 'midnight'
# Downloading s3://stg-objectlock/s3v/test.txt >>> test.txt...
# will use version from 2026-02-10 17:22:31+00:00 which is the latest version older than specified time 2026-02-11 00:00:00+00:00
  Using version: EouOCDXQpn6xvA9LOXhlB6JITw_DZj_0
# Successfully downloaded (2) to test.txt
```



### Delete and undelete

`s3v rm` deletes file. After deletion, `aws s3 ls` do not list file, but `s3v ls` still shows it with `[DEL]` tag.

```bash
$ s3v rm stg-objectlock/s3v/test.txt
$ aws s3 ls stg-objectlock/s3v/
$ s3v ls stg-objectlock/s3v/
test.txt                                |2026-02-10 16:35:00|              2|   4| [DEL]
```

If we will see versions for file, we will see special delete marker on S3 (which makes file to be logically 'deleted').
```bash
$ s3v ls stg-objectlock/s3v/test.txt
Objects under prefix 's3v/test.txt':
s3v/test.txt [deleted]
   by0fQCa9Jl7gFgl8vKEjaDvl8z3CSRnD          2  2026-02-10 16:21:30
   LHK6nA8Ny5YHNh7TOoH94LDinqCH9Czt          2  2026-02-10 16:21:46
   iIGXCsBmEKvBq7DhaP09DIzp3fLO9d1H          2  2026-02-10 16:21:55
   odaXkvFlMoAWwDu_q.K3esuYdHjUpgMg  [DELETED]  2026-02-10 16:40:33
```

`s3v unrm` will remove "delete marker" and file (latest version) will be available again.
```bash
$ s3v unrm stg-objectlock/s3v/test.txt

$ s3v ls stg-objectlock/s3v/
test.txt                                |2026-02-10 16:35:00|              2|   3|
```

`s3v wipe` will delete ALL VERSIONS of speficied object.
```
$ s3v wipe s3://stg-objectlock/test_file_1770544464743.txt
# Wiping s3://stg-objectlock/test_file_1770544464743.txt (deleting all versions and delete markers)...
# Successfully wiped s3://stg-objectlock/test_file_1770544464743.txt from history (deleted 2 versions/delete markers)
```

### Restore specific version
To recover specific version of file (make it to be current) use `s3v recover` (or just `s3v r`). Let's recover first version of file.

```bash
$ s3v recover stg-objectlock/s3v/test.txt . -s by0fQCa9Jl7gFgl8vKEjaDvl8z3CSRnD
Successfully recovered version by0fQCa9Jl7gFgl8vKEjaDvl8z3CSRnD as current version of s3://stg-objectlock/s3v/test.txt

$ s3v cp stg-objectlock/s3v/test.txt . 
$ cat test.txt 
1
```

