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

[
    runTests()
]
