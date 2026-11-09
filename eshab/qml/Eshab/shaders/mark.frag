#version 440
// The «الملف ينسحب» mark as a signed distance field: a page whose top-left
// corner became a drop sitting in a round notch. Same field as
// eshab/identity/mark.py; Logo.qml animates the uniforms.

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec4 page;      // centre x, centre y, half width, half height (100 x 100 box)
    vec4 notch;     // centre x, centre y, radius, page corner radius
    vec4 drop;      // centre x, centre y, radius, liquid fillet
    vec4 neck;      // radius at the rim, radius at the drop, box units per pixel, text lines (0/1)
    vec4 lightTone; // material, lit side
    vec4 deepTone;  // material, deep side
    vec4 matter;    // body alpha, rim strength, fill level (<0 = solid), wave phase
    vec4 extra;     // check reveal 0..1, flat (0 = glass, 1 = single colour), unused, unused
};

float sdRoundBox(vec2 p, vec2 c, vec2 h, float r) {
    vec2 q = abs(p - c) - (h - r);
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

float sdCircle(vec2 p, vec2 c, float r) { return length(p - c) - r; }

float sdUnevenCapsule(vec2 p, vec2 a, vec2 b, float ra, float rb) {
    vec2 d = b - a;
    float h = length(d);
    if (h < 1e-4) return length(p - a) - max(ra, rb);
    vec2 u = d / h;
    vec2 q = p - a;
    vec2 l = vec2(abs(q.x * u.y - q.y * u.x), dot(q, u));
    float bb = (ra - rb) / h;
    float aa = sqrt(max(0.0, 1.0 - bb * bb));
    float k = dot(l, vec2(-bb, aa));
    if (k < 0.0) return length(l) - ra;
    if (k > aa * h) return length(l - vec2(0.0, h)) - rb;
    return dot(l, vec2(aa, bb)) - ra;
}

float smin(float a, float b, float k) {
    float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
    return mix(b, a, h) - k * h * (1.0 - h);
}

float smax(float a, float b, float k) { return -smin(-a, -b, k); }

vec2 rimPoint() {
    vec2 toPage = page.xy - notch.xy;
    return notch.xy + normalize(toPage) * notch.z;
}

float pageBody(vec2 p) {
    float box = sdRoundBox(p, page.xy, page.zw, notch.w);
    return smax(box, -sdCircle(p, notch.xy, notch.z), drop.w);
}

float shape(vec2 p) {
    float d = smin(pageBody(p), sdCircle(p, drop.xy, drop.z), drop.w);
    if (neck.x > 0.0 || neck.y > 0.0)
        d = smin(d, sdUnevenCapsule(p, rimPoint(), drop.xy, neck.x, neck.y), drop.w * 2.0);
    return d;
}

float textLines(vec2 p) {
    float right = page.x + page.z - 10.0;
    float first = sdUnevenCapsule(p, vec2(right - 24.0, page.y - 6.0), vec2(right, page.y - 6.0), 2.2, 2.2);
    float second = sdUnevenCapsule(p, vec2(right - 15.0, page.y + 4.0), vec2(right, page.y + 4.0), 2.2, 2.2);
    return min(first, second);
}

float checkMark(vec2 p, float reveal) {
    vec2 a = page.xy + vec2(-11.0, 2.0);
    vec2 b = page.xy + vec2(-3.0, 10.0);
    vec2 c = page.xy + vec2(12.0, -8.0);
    float first = clamp(reveal * 2.6, 0.0, 1.0);
    float second = clamp(reveal * 2.6 - 1.0, 0.0, 1.6) / 1.6;
    float d = sdUnevenCapsule(p, a, mix(a, b, first), 3.2, 3.2);
    if (second > 0.0) d = min(d, sdUnevenCapsule(p, b, mix(b, c, second), 3.2, 3.2));
    return d;
}

float bevelHeight(float d) {
    float s = clamp(-d / 9.0, 0.0, 1.0);
    return sqrt(1.0 - (1.0 - s) * (1.0 - s));
}

void main() {
    float unit = neck.z;
    vec2 p = qt_TexCoord0 * 100.0;
    float d = shape(p);
    float coverage = clamp(0.5 - d / unit, 0.0, 1.0);
    if (coverage <= 0.0) { fragColor = vec4(0.0); return; }

    if (extra.y > 0.5) {
        float flatD = neck.w > 0.5 ? max(d, -textLines(p)) : d;
        float flatCover = clamp(0.5 - flatD / unit, 0.0, 1.0);
        fragColor = vec4(lightTone.rgb, 1.0) * flatCover * qt_Opacity;
        return;
    }

    // Finite differences keep the lighting identical on D3D, Vulkan and GL.
    float h = bevelHeight(d);
    vec2 grad = vec2(bevelHeight(shape(p + vec2(unit, 0.0))) - h,
                     bevelHeight(shape(p + vec2(0.0, unit))) - h) / unit;
    vec3 n = normalize(vec3(-grad * 3.2, 1.0));

    vec3 lightDir = normalize(vec3(-0.45, -0.62, 0.64));
    vec3 halfDir = normalize(lightDir + vec3(0.0, 0.0, 1.0));
    float diffuse = clamp(dot(n, lightDir), 0.0, 1.0);
    float spec = pow(clamp(dot(n, halfDir), 0.0, 1.0), 70.0);
    float fresnel = pow(1.0 - n.z, 1.6);

    float s = clamp(-d / 9.0, 0.0, 1.0);
    float t = clamp(((p.x - 20.0) + (p.y - 10.0)) / 150.0 + 0.25 * (1.0 - s), 0.0, 1.0);
    vec3 tone = mix(lightTone.rgb, deepTone.rgb, t);
    float bodyAlpha = matter.x;

    // Loading: clear glass page that fills with the material from the bottom.
    if (matter.z >= 0.0) {
        float top = page.y - page.w;
        float bottom = page.y + page.w;
        float level = mix(bottom + 2.0, top - 2.0, matter.z) + 1.4 * sin(p.x * 0.19 + matter.w);
        float liquid = clamp((p.y - level) / unit + 0.5, 0.0, 1.0);
        float inDrop = clamp(0.5 - sdCircle(p, drop.xy, drop.z) / unit, 0.0, 1.0);
        liquid = max(liquid, inDrop);
        tone = mix(vec3(0.93, 0.95, 0.98), tone, liquid);
        bodyAlpha = mix(0.30, bodyAlpha, liquid);
    }

    vec3 color = tone * (0.78 + 0.32 * diffuse);
    float edge = clamp(1.0 + d / 1.6, 0.0, 1.0);
    float facing = clamp(-(n.x * 0.6 + n.y * 0.8), 0.0, 1.0);
    color = mix(color, vec3(1.0), matter.y * fresnel * (0.4 + 0.6 * facing));
    color = mix(color, vec3(1.0), 0.85 * spec);
    color = mix(color, vec3(1.0), 0.55 * edge * facing);
    color *= 1.0 - 0.18 * edge * (1.0 - facing);
    float alpha = coverage * (bodyAlpha + (1.0 - bodyAlpha) * clamp(fresnel * 1.4 + spec, 0.0, 1.0));

    float mark = 1e3;
    if (neck.w > 0.5 && extra.x <= 0.0) mark = textLines(p);
    if (extra.x > 0.0) mark = checkMark(p, extra.x);
    float etch = clamp(0.5 - mark / unit, 0.0, 1.0) * coverage;
    color = mix(color, vec3(1.0), (extra.x > 0.0 ? 0.92 : 0.62) * etch);
    alpha = max(alpha, etch * 0.9);

    fragColor = vec4(clamp(color, 0.0, 1.0) * alpha, alpha) * qt_Opacity;
}
