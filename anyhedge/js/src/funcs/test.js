export function sum(a, b) {
    return {
        "sum": a + b,
    }
}

export async function asyncSum(a, b) {
    return { sum: a + b }
}
