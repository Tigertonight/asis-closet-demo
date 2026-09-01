
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
uniform sampler2D _BaseTexture1;
uniform sampler2D fgLut;
uniform sampler2D bgLut;
// uniform float adjustable_bg_filter;
// uniform float adjustable_fg_filter;
uniform float adjustable_filter_intensity;



vec4 lm_take_effect_filter(sampler2D filterTex,vec4 inputColor,float uniAlpha)
{
  highp vec4 textureColor= inputColor;
  highp float blueColor=textureColor.b*63.;
  
  highp vec2 quad1;
  quad1.y=floor(floor(blueColor)/8.);
  quad1.x=floor(blueColor)-(quad1.y*8.);
  
  highp vec2 quad2;
  quad2.y=floor(ceil(blueColor)/8.);
  quad2.x=ceil(blueColor)-(quad2.y*8.);
  
  highp vec2 texPos1;
  texPos1.x=(quad1.x*1./8.)+.5/512.+((1./8.-1./512.)*textureColor.r);
  texPos1.y=(quad1.y*1./8.)+.5/512.+((1./8.-1./512.)*textureColor.g);
  texPos1.y=1.-texPos1.y;
  highp vec2 texPos2;
  texPos2.x=(quad2.x*1./8.)+.5/512.+((1./8.-1./512.)*textureColor.r);
  texPos2.y=(quad2.y*1./8.)+.5/512.+((1./8.-1./512.)*textureColor.g);
  texPos2.y=1.-texPos2.y;
  vec4 newColor1=texture2D(filterTex,texPos1);
  vec4 newColor2=texture2D(filterTex,texPos2);
  vec4 newColor=mix(newColor1,newColor2,fract(blueColor));
  newColor = mix(textureColor,vec4(newColor.rgb,textureColor.w),uniAlpha);

  return newColor;
}

void main()
{
    vec4 pass1 = texture(_BaseTexture0, v_texcoord);
    vec4 bgColor = lm_take_effect_filter(bgLut, pass1, adjustable_filter_intensity / 100.0);
    vec4 fgColor = lm_take_effect_filter(fgLut, pass1, adjustable_filter_intensity / 100.0);
    vec4 mask = texture(_BaseTexture1, v_texcoord);
    vec4 result = mix(bgColor, fgColor, mask.r);
    fragColor = result;
    // fragColor = mask;
    // fragColor = vec4(1.0, 0.0, 0.0, 1.0);
    
}
