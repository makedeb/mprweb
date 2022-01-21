#!/bin/bash

cd /aurweb

aurweb-mkpkglists --extended
if [ $? -eq 0 ]; then
    echo "[$(date -u)] executed mkpkglists" >> /var/log/mkpkglists.log
fi

exec /usr/bin/crond -nx proc
