.pragma library

// Small formatting helpers shared by the editor's pieces.

function two(n) {
    return (n < 10 ? "0" : "") + n
}

// 75.25 -> "1:15" (or "1:15.2" when precise); hours appear only when needed.
function time(seconds, precise) {
    if (!isFinite(seconds) || seconds < 0)
        seconds = 0
    let whole = Math.floor(seconds)
    let tenth = Math.floor((seconds - whole) * 10 + 1e-6)
    if (tenth > 9) { tenth = 0; whole += 1 }
    const h = Math.floor(whole / 3600)
    const m = Math.floor((whole % 3600) / 60)
    const s = whole % 60
    let out = h > 0 ? h + ":" + two(m) + ":" + two(s) : m + ":" + two(s)
    if (precise)
        out += "." + tenth
    return out
}

// "Keeps {t}" with {t} filled in.
function fill(template, values) {
    let out = String(template)
    for (const key in values)
        out = out.split("{" + key + "}").join(String(values[key]))
    return out
}

function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value))
}

// "16:9" -> 1.777…, "free" -> 0, "original" -> the picture's own shape.
function ratio(aspect, width, height) {
    if (!aspect || aspect === "free")
        return 0
    if (aspect === "original")
        return height > 0 ? width / height : 0
    const parts = String(aspect).split(":")
    if (parts.length !== 2)
        return 0
    const a = parseFloat(parts[0]), b = parseFloat(parts[1])
    return a > 0 && b > 0 ? a / b : 0
}

function hasArabic(text) {
    return /[֐-ࣿ]/.test(String(text))
}
