# s3v
Convinient CLI tool to work with versioned S3 buckets. Like `aws s3` or `aws s3api` but much easier to use.

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

We upload three versions of same file, each one will overwrite old copy. In "ls" we see filename, last modification time, size of latest copy and number of versions in storage.

### Upload

```bash
$ echo 1 > test.txt 
$ s3v cp test.txt s3://stg-objectlock/s3v/
$ echo 2 > test.txt 
$ s3v cp test.txt s3://stg-objectlock/s3v/
$ echo 3 > test.txt 
$ s3v cp test.txt s3://stg-objectlock/s3v/
```
You can also give full target name like s3://stg-objectlock/s3v/test.txt. `s3://` prefix is optional ()


### List
Now, list contents of s3v logical 'folder' (all objects with name starting with `s3v/`). If we give full name of object, ls will list all versions.

```bash
$ s3v ls stg-objectlock/s3v
Listing objects in bucket 'stg-objectlock' with prefix 's3v'
test.txt                                |2026-02-10 16:21:55|              2|   3|

$ s3v ls stg-objectlock/s3v/test.txt
Listing objects in bucket 'stg-objectlock' with prefix 's3v/test.txt'
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

Give `-i VERSION` to download specific version.

```bash
$ s3v cp stg-objectlock/s3v/test.txt . -s by0fQCa9Jl7gFgl8vKEjaDvl8z3CSRnD
  Using version: by0fQCa9Jl7gFgl8vKEjaDvl8z3CSRnD
$ cat test.txt 
1
```


### Delete and undelete

`s3v rm` deletes file. After deletion, `aws s3 ls` do not list file, but `s3v ls` still shows it with `[DEL]` tag.

```bash
$ s3v rm stg-objectlock/s3v/test.txt
$ aws s3 ls stg-objectlock/s3v/
$ s3v ls stg-objectlock/s3v/
Listing objects in bucket 'stg-objectlock' with prefix 's3v/'
test.txt                                |2026-02-10 16:35:00|              2|   4| [DEL]
```

If we will see versions for file, we will see special delete marker on S3 (which makes file to be logically 'deleted').
```bash
 $ s3v ls stg-objectlock/s3v/test.txt
Listing objects in bucket 'stg-objectlock' with prefix 's3v/test.txt'
# Fetching version metadata for bucket: stg-objectlock...
# Fetched metadata for 215 versions from 153 object(s) in bucket 'stg-objectlock'
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
Listing objects in bucket 'stg-objectlock' with prefix 's3v/'
test.txt                                |2026-02-10 16:35:00|              2|   3|
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

