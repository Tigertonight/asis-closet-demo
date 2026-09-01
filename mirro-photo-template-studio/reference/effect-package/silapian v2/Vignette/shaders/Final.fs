
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
    uniform sampler2D _BaseTexture1;//lut
    
    uniform float adjustable_x;
    uniform float adjustable_y;
    uniform float adjustable_intensity;

    uniform float slope;
    uniform float bias;

    uniform sampler2D maskN;
    uniform sampler2D maskZ;
vec4 caculLut(vec4 inColor){
    float g = inColor.g * 16.0;
    float v = (0.5 / 17.0) + inColor.r * (1.0 - 1.0 / 17.0);
    float b = inColor.b * 16.0 / 17.0 + (0.5 / 17.0);
    float u1 = b / 17.0 + floor(g) / 17.0;
    float u2 = b / 17.0 + ceil(g) / 17.0;
    vec4 newColor1 = texture2D(_BaseTexture1, vec2(u1, v));
    vec4 newColor2 = texture2D(_BaseTexture1, vec2(u2, v));
    return mix(newColor1, newColor2, fract(g));
 }

    void main()
{
    vec4 textureColor = texture(_BaseTexture0, v_texcoord);
    vec4 baseColor = caculLut(textureColor);

    vec3 result = slope * baseColor.rgb + bias;
    result = clamp(result, 0.0, 1.0);
    vec4 blackAndWhite = vec4(result, baseColor.a);

    // 始终使用 maskN，不再根据 Vignette 正负选择 maskZ
    vec4 maskNColor = texture(maskN, v_texcoord);
    vec4 maskValue = maskNColor;

    // 混合因子，确保在 [0, 1] 范围内
    float factor = maskValue.a * clamp(abs(adjustable_intensity), 0.0, 100.0) * (0.32 / 100.0);

    // 正片叠底混合：base * blend
    vec4 blended = blackAndWhite * maskValue;

    // 混合原颜色与正片叠底后的颜色，根据 factor 控制强度
    vec4 VignetteColor = mix(blackAndWhite, blended, factor);

    // 保留原颜色的 alpha 通道
    fragColor = vec4(VignetteColor.rgb, blackAndWhite.a);

    // 保持原 alpha 通道的 clamp 操作
    fragColor = clamp(fragColor, 0.0, fragColor.a);
}

    