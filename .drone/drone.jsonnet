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
    type: "exec",
    trigger: {branch: ["mprweb"]},
    depends_on: ["run-tests"],
    node: {server: "mprweb"},
    steps: [{
        name: "publish-image",
        image: "ubuntu",
        environment: {
            mpr_db_password: {from_secret: "mpr_db_password"},
            mpr_smtp_password: {from_secret: "mpr_smtp_password"}
        },
        commands: [
            "bash .drone/scripts/publish-image.sh"
        ]
    }]
};

[
    runTests(),
    publishImage()
]
