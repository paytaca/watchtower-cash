// Palace
export const hdPrivateKeyLive1 = 'xprv9yiDrLfDQve2eaCzsHtzkqzjtsXarDnogGVvJFw3SNaaytjPPeDpsQoe4ieGELPy2uvm2zfC86KvdF7zRmYp6CgFpG9ZWHnJkiU2Vjy4EyH'
export const hdPublicKeyLive1 = 'xpub6ChaFrC7FJCKs4HTyKS17ywUSuN5FgWf3VRX6eLezi7Zrh4XwBY5RD87v1bJTAf3Vf71bfMAWCMEd1G3mQdNMiFhYVmRj3Gg1m7ReSR5KHk'
export const privateKeyZeroLive1 = 'Ky6999dBwFqX4kDewhoFkzUj9deS1W32YvAQcA22wNvJK6nNvCeW'

// Truly
export const hdPrivateKeyLive2 = 'xprv9z79WuZyB6KuoKqtLgJosPSus8cdS2EaPL4ZjKhtgfoqV3jopbrT9Kw51PRABBUL9g6au3z2TJGE5BUuWDNDubk2Lt2HefhYWRFJpjd8Psv'
export const hdPublicKeyLive2 = 'xpub6D6VvR6s1TtD1ovMShqpEXPeRAT7qUxRkYzAXi7WF1LpMr4xN9Ahh8FYrfh3zKEKQUUPvjc9p8syMpctuVuc586PXooQGMjzX5ZK3HrDhuG'

// Case
export const hdPrivateKeyLive3  = 'xprv9ya6oMNmyUZuoewSZJYDq7QtMDhj2BdajNADryKiVWCgWeUKp8L6qHwN2gHhkX4h17zQj6PV1JPa4WwnbMDvoRU3wwoSXfPZvFHEw9CMcex'
export const hdPublicKeyLive3   = 'xpub6CZTCrufor8D291ufL5ECFMcuFYDReMS6b5pfMjL3qjfPSoUMfeMP6FqsvfXbywcwQDD88sriRZDrbKbauStkBuEV5igshUHRMhq5BLrXRp'

export const TwoOfThreeReal = {
    name: '2 of 3 Multisig Real Paytaca Wallet Signers',
    m: 2,
    signers: [
        {
            name: 'Palace',
            xpub: hdPublicKeyLive1,
            xprv: hdPrivateKeyLive1
        },
        {
            name: 'Truly',
            xpub: hdPublicKeyLive2,
            xprv: hdPrivateKeyLive2
        },
        {
            name: 'Case',
            xpub: hdPublicKeyLive3,
            xprv: hdPrivateKeyLive3
        }
    ]
}
