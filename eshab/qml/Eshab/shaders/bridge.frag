#version 440
// The liquid bridge from the orb to the chosen card: a tapered capsule with
// a waist, in the material colour, with a highlight running along it.

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec4 ends;      // a.x, a.y, b.x, b.y in item pixels
    vec4 radii;     // radius at a, radius at b, waist (0..1), item width
    vec4 tone;      // material colour, a = alpha
    vec4 extra;     // item height, unused...
};

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

void main() {
    vec2 size = vec2(radii.w, extra.x);
    vec2 p = qt_TexCoord0 * size;
    vec2 a = ends.xy;
    vec2 b = ends.zw;
    float h = max(length(b - a), 1e-3);
    // Thinner in the middle: a liquid neck, not a rod.
    float t = clamp(dot(p - a, b - a) / (h * h), 0.0, 1.0);
    float waist = 1.0 - radii.z * 4.0 * t * (1.0 - t);
    float d = sdUnevenCapsule(p, a, b, radii.x * waist, radii.y * waist);
    float coverage = clamp(0.5 - d, 0.0, 1.0);
    if (coverage <= 0.0) { fragColor = vec4(0.0); return; }

    float r = mix(radii.x, radii.y, t) * waist;
    float across = clamp(-d / max(r, 1.0), 0.0, 1.0);    // 0 at the edge, 1 on the axis
    vec3 color = tone.rgb * (0.82 + 0.25 * across);
    color = mix(color, vec3(1.0), 0.55 * pow(across, 6.0)); // highlight along the axis
    color = mix(color, vec3(1.0), 0.35 * clamp(1.0 + d / 1.2, 0.0, 1.0)); // rim
    float alpha = coverage * tone.a;
    fragColor = vec4(color * alpha, alpha) * qt_Opacity;
}
