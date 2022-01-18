local runTests() = {
    name: "run-tests",
    kind: "pipeline",
    type: "docker",

    steps: [{
        name: "run-tests",
        image: "archlinux:base-devel",
        environment: {
            AUR_CONFIG: "conf/config",
            DB_HOST: "localhost",
            TEST_RECURSION_LIMIT: 10000,
        },

        commands: [
            "bash .drone/scripts/run-tests.sh"
        ]
    }]
};

local publishImage() = {
    name: "publish-image",
    kind: "pipeline",
    type: "docker",
	trigger: {branch: ["mprweb"]},
    depends_on: ["run-tests"],
    volumes: [
        {
            name: "docker",
            host: {path: "/var/run/docker.sock"}
        },

        {
            name: "binaries",
            host: {path: "/usr/bin/docker-compose"}
        },

        {
            name: "mprweb",
            host: {path: "/var/www/mpr.hunterwittenborn.com"}
        }
    ],

    steps: [{
        name: "publish-image",
        image: "ubuntu",
        environment: {
            mpr_db_password: {from_secret: "mpr_db_password"},
            mpr_smtp_password: {from_secret: "mpr_smtp_password"}
        },
        volumes: [
            {
                name: "docker",
                path: "/var/run/docker.sock"
            },

            {
                name: "binaries",
                path: "/usr/bin/docker-compose"
            },

            {
                name: "mprweb",
                path: "/var/www/mpr.hunterwittenborn.com"
            }
        ],
        commands: [
            "apt-get update",
            "apt-get install docker.io python3 -yq",
            "bash .drone/scripts/publish-image.sh"
        ]
    }]
};

[
    runTests(),
    publishImage()
]
