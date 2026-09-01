
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
    uniform sampler2D lut0;

    uniform float Brightness;
    uniform float Contrast;
    uniform float Shadow;
    uniform float Highlight;
    uniform float Temperature;
    uniform float Tone;
    uniform float LightSensation;
    uniform float Saturation;
    uniform float Fade;
    uniform float Exposure;
    uniform float Vibrance;

    uniform float adjustable_x;
    uniform float adjustable_y;

    const float brightnessInLutRow = 1.0;
    const float contrastInLutRow = 2.0;
    const float exposureInLutRow = 3.0;
    const float fadeInLutRow = 4.0;
    const float highlightInLutRow = 5.0;
    const float lightSensationInLutRow = 6.0;
    const float saturationInLutRow = 7.0;
    const float shadowInLutRow = 8.0;
    const float temperatureInLutRow = 9.0;
    const float toneInLutRow = 10.0;
    const float vibranceInLutRow = 11.0;

    const float lut_scale_row_y = 1.0 / 22.0;
    const float lut_scale_17 = 1.0 / 17.0;

//用于min、max两张LUT图合并的情况，minLUT在上方，maxLUT在下方
vec4 locationEffectByTextureMap(vec4 baseColor, float intensity, float rowInLut)
{
    float slider_progress = abs(intensity);
    vec4 curColor = baseColor;
    vec4 textureColor = curColor;
    float blueColor = curColor.b * (17.0 - 1.0);
    vec2 standardTableSize = vec2(289.0, 17.0);
    vec2 pixelSize = 1.0 / standardTableSize;
    vec2 quad1 = vec2(0.0);
    quad1.y = floor(floor(blueColor) * lut_scale_17);
    quad1.x = floor(blueColor) - (quad1.y * 1.0);
    vec2 quad2;
    quad2.y = floor(ceil(blueColor) * lut_scale_17);
    quad2.x = ceil(blueColor) - (quad2.y * 1.0);
    vec2 texPos1;
    texPos1.x = (quad1.x * 1.0 * lut_scale_17) + 0.5 / standardTableSize.x + ((1.0 * lut_scale_17 - 1.0 / standardTableSize.x) * textureColor.r);
    texPos1.y = (quad1.y * 1.0 / 1.0) + 0.5 / standardTableSize.y + ((1.0 / 1.0 - 1.0 / standardTableSize.y) * textureColor.g);
    texPos1.y = texPos1.y * lut_scale_row_y + lut_scale_row_y * (rowInLut - 1.0) * 2.0;
    vec2 texPos2;
    texPos2.x = (quad2.x * 1.0 * lut_scale_17) + 0.5 / standardTableSize.x + ((1.0 * lut_scale_17 - 1.0 / standardTableSize.x) * textureColor.r);
    texPos2.y = (quad2.y * 1.0 / 1.0) + 0.5 / standardTableSize.y + ((1.0 / 1.0 - 1.0 / standardTableSize.y) * textureColor.g);
    texPos2.y = texPos2.y * lut_scale_row_y + lut_scale_row_y * (rowInLut - 1.0) * 2.0;

    float alpha = fract(blueColor);
    vec4 newColor = vec4(0.0);
    if (intensity > 0.0) { // 因为对两张LUT图做了合并，上半部分对应于intensity < 0.0的情况，下半部分对应于intensity > 0.0的情况
        texPos1.y = texPos1.y + lut_scale_row_y;
        texPos2.y = texPos2.y + lut_scale_row_y;
    }
    vec4 newColor1 = texture2D(lut0, texPos1);
    vec4 newColor2 = texture2D(lut0, texPos2);
    newColor = mix(newColor1, newColor2, alpha);
    newColor = mix(curColor,newColor,slider_progress);
    return newColor;
}


void main()
{

    //uniform map
    float _brightness       = Brightness*0.01;
    float _contrast         = Contrast*0.01;
    float _exposure         = Exposure*0.01;
    float _vibrance         = Vibrance*0.01;
    float _saturation       = Saturation*0.01;
    float _highlight        = Highlight*0.01;
    float _shadow           = Shadow*0.01;
    float _tone             = Tone*0.01;
    float _temperature      = Temperature*0.01;
    float _lightsensation   = LightSensation*0.01;
    float _fade             = Fade*0.01;


    vec4 baseColor;
    baseColor.r = (17.0 / 16.0) * v_texcoord.y - 0.5 / 16.0;
    baseColor.g = floor (v_texcoord.x * 17.0) / 16.0;
    baseColor.b = (v_texcoord.x - floor(v_texcoord.x * 17.0) * lut_scale_17) * 17.0;
    baseColor.b = 17.0 / 16.0 * baseColor.b - 0.5 / 16.0;
    baseColor.a = 1.0;

    if(abs(_brightness) > 0.01){
        baseColor = locationEffectByTextureMap(baseColor, _brightness, brightnessInLutRow);
    }
    if(abs(_contrast) > 0.01){
        baseColor = locationEffectByTextureMap(baseColor, _contrast, contrastInLutRow);
    }
    if (abs(_shadow) > 0.01) { // 总是有Shadow >= 0，inputBrightnessMin仅用于填充第二个参数的位置
        baseColor = locationEffectByTextureMap(baseColor, _shadow, shadowInLutRow);
    }
    if (abs(_highlight) > 0.01) {
        baseColor = locationEffectByTextureMap(baseColor, _highlight, highlightInLutRow);
    }
    if(abs(_temperature) > 0.01){
        baseColor = locationEffectByTextureMap(baseColor, _temperature, temperatureInLutRow);
    }
    if(abs(_tone) > 0.01){
        baseColor = locationEffectByTextureMap(baseColor, _tone, toneInLutRow);
    }
    if(abs(_saturation) > 0.01){
        baseColor = locationEffectByTextureMap(baseColor, _saturation, saturationInLutRow);
    }
    if (abs(_lightsensation) > 0.01) {
        baseColor = locationEffectByTextureMap(baseColor, _lightsensation, lightSensationInLutRow);
    }
    if (_fade > 0.01) { // 总是有Fade >= 0，inputBrightnessMin仅用于填充第二个参数的位置
        baseColor = locationEffectByTextureMap(baseColor, _fade, fadeInLutRow);
    }
    if (abs(_exposure) > 0.01) {
        baseColor = locationEffectByTextureMap(baseColor, _exposure, exposureInLutRow);
    }
    if (abs(_vibrance) > 0.01) {
        baseColor = locationEffectByTextureMap(baseColor, _vibrance, vibranceInLutRow);
    }
    fragColor =  baseColor;
    //fragColor =  texture(_BaseTexture0, v_texcoord);
}
