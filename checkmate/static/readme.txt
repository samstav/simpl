Layout:

Trying to keep versioning clean, avoid duplication, and make it predictable to
where to find things.

- All libraries go in /lib.
- Each library gets a folder, unless it consists of one file (a .min extra file
  doesn't count, so jquery, for eample, has two files in /lib)
- The folder must contain a version identifier (ex. /lib/bootstrap-2.0.4)
- Put file types in /img, /css. and /js IF it is option. Some libraries
  hard-code those; we don't need to modify that.
- If desired, create an unversioned folder for the latest version of a library
  (ex. /bootstrap containing a copy of /bootstrap-2.0.4). So consumers can link
  to latest and deal with breaking changes, or link to a fixed version.
- Add a readme in a folder if there is something special about it (for example,
  the boostrap download is using the precompiled option available from their
  site which includes all plugins in bootstrap.js)

Exceptions are fine, but document in read me if possible.