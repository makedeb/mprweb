#!/bin/bash
cd /aurweb

# Running the scripts here allows us to get a quick look at if everything is working right.
aurweb-mkpkglists --extended
aurweb-pkgmaint
aurweb-usermaint
aurweb-popupdate
aurweb-tuvotereminder
aurweb-oodcheck

exec /usr/bin/crond -nx proc
