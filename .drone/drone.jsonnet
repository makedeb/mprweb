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
    depends_on: ["run-tests"],
    volumes: [{name: "docker", host: {"path": "/var/run/docker.sock"}}],

    steps: [{
        name: "publish-image",
        image: "docker",
        volumes: [{name: "docker", path: "/var/run/docker.sock"}],
        environment: {
            proget_api_key: {from_secret: "proget_api_key"}
        },  
            
        commands: [
            "apk add --no-cache bash",
            "bash .drone/scripts/publish-image.sh"
        ]
    }]
};

[
    runTests(),
    publishImage()
]
