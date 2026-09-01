#ifdef GL_ES
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else 
precision mediump float;
#endif
#endif

in vec2 v_texcoord;
out vec4 fragColor;
uniform sampler2D _BaseTexture0;
uniform float adjustable_noise_point;

// 2D Fake Random
float random(vec2 st) {
    return fract(sin(dot(st.xy, vec2(12.9898, 78.233))) * 43758.5453123);
}

void main() {
    float uTime = 1.0;
    float intensity = adjustable_noise_point / 100.0;
    float strength = 9.6 * intensity;
    float x = (v_texcoord.x + random(v_texcoord)) * (v_texcoord.y + random(v_texcoord)) * ((mod(uTime, 100.0) + 3.0) * 10.0 * intensity);
    vec4 grainColor = vec4(mod((mod(x, 13.0) + 1.0) * (mod(x, 123.0) + 1.0), 0.01) - (0.005 * (1.0 - step(intensity, 0.0)))) * strength;
    
    vec4 srcColor = texture2D(_BaseTexture0, v_texcoord);
    srcColor.rgb += grainColor.rgb;

    fragColor = srcColor;
}
