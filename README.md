# mprweb

mprweb is a hosting platform for the makedeb Package Repository (MPR), a fork of
aurweb, the underlying platform that powers the Arch User Repository (AUR).
The scripts contained in the repository can be built using `makedeb`
and installed using Debian package managers such as `dpkg` and `apt`.

The mprweb project includes:

* A web interface to search for packaging scripts and display package details.
* An SSH/Git interface to submit and update packages and package meta data.
* Community features such as comments, votes, package flagging and requests.
* Editing/deletion of packages and accounts by Trusted Users and Developers.
* Area for Trusted Users to post MPR-related proposals and vote on them.

## Directory Layout

* `aurweb`: aurweb Python modules, Git interface and maintenance scripts
* `conf`: configuration and configuration templates
* `static`: static resource files
* `templates`: jinja2 template collection
* `doc`: project documentation
* `po`: translation files for strings in the aurweb interface
* `schema`: schema for the SQL database
* `test`: test suite and test cases
* `upgrading`: instructions for upgrading setups from one release to another
* `web`: PHP-based web interface for the MPR

Documentation
-------------

| What         | Link                                             |
|--------------|--------------------------------------------------|
| Installation | [INSTALL](./INSTALL)                             |
| Testing      | [test/README.md](./test/README.md)               |
| Git          | [doc/git-interface.txt](./doc/git-interface.txt) |
| Maintenance  | [doc/maintenance.txt](./doc/maintenance.txt)     |
| RPC          | [doc/rpc.txt](./doc/rpc.txt)                     |
| Docker       | [doc/docker.md](./doc/docker.md)                 |

Testing
-------

See [test/README.md](test/README.md) for details on dependencies and testing.
