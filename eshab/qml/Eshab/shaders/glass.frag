#version 440
// Eshab's liquid glass for cards, the orb and pills: the frosted desktop
// behind the item, bent a little at the rim like a lens, a neutral or
// material tint, a bright rim on the lit side and a soft shadow below.
// The item is larger than the glass by `pad` on every side (for the shadow).

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec4 frostRect;   // where this item sits in the frost texture: u, v, width, height
    vec4 shape;       // item width, item height (px), corner radius, pad
    vec4 tint;        // neutral glass colour, a = strength
    vec4 accent;      // material colour, a = strength while selected
    vec4 light;       // rim strength, shadow strength, refraction px, dark (0/1)
};
layout(binding = 1) uniform sampler2D frost;

float sdRoundBox(vec2 p, vec2 h, float r) {
    vec2 q = abs(p) - (h - r);
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

void main() {
    vec2 size = shape.xy;
    float pad = shape.w;
    vec2 p = qt_TexCoord0 * size - size * 0.5;
    vec2 half_ = size * 0.5 - vec2(pad);
    float radius = min(shape.z, min(half_.x, half_.y));
    float d = sdRoundBox(p, half_, radius);

    // Soft shadow under the glass, a few pixels down.
    float shadowD = sdRoundBox(p - vec2(0.0, 4.0), half_, radius);
    float shadow = light.y * (1.0 - smoothstep(-2.0, pad * 0.9, shadowD));

    float coverage = clamp(0.5 - d, 0.0, 1.0);
    if (coverage <= 0.0) {
        fragColor = vec4(0.0, 0.0, 0.0, shadow) * qt_Opacity;
        return;
    }

    // Normal of the rounded box (finite differences), strongest at the rim.
    float e = 1.0;
    vec2 n = vec2(sdRoundBox(p + vec2(e, 0.0), half_, radius) - sdRoundBox(p - vec2(e, 0.0), half_, radius),
                  sdRoundBox(p + vec2(0.0, e), half_, radius) - sdRoundBox(p - vec2(0.0, e), half_, radius));
    n = length(n) > 0.0 ? normalize(n) : vec2(0.0);
    float rimBand = 1.0 - clamp(-d / 9.0, 0.0, 1.0);
    vec2 bend = -n * rimBand * rimBand * light.z;

    vec2 uv = frostRect.xy + (qt_TexCoord0 + bend / size) * frostRect.zw;
    vec3 back = texture(frost, clamp(uv, vec2(0.001), vec2(0.999))).rgb;

    vec3 color = mix(back, tint.rgb, tint.a);
    color = mix(color, accent.rgb, accent.a);

    // Lit from the top-left: a bright rim there, a faint dark one opposite.
    float facing = clamp(dot(n, normalize(vec2(-0.55, -0.85))), -1.0, 1.0);
    float rim = clamp(1.0 - abs(d + 0.8) / 1.1, 0.0, 1.0);
    color = mix(color, vec3(1.0), rim * light.x * (0.35 + 0.65 * max(facing, 0.0)));
    color *= 1.0 - rim * 0.25 * max(-facing, 0.0);
    // A broad, faint sheen on the upper half.
    float sheen = (1.0 - qt_TexCoord0.y) * (1.0 - light.w * 0.6) * 0.07;
    color += vec3(sheen);

    vec4 glass = vec4(clamp(color, 0.0, 1.0), 1.0) * coverage;
    fragColor = (glass + vec4(0.0, 0.0, 0.0, shadow) * (1.0 - coverage)) * qt_Opacity;
}
