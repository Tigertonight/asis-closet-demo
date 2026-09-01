in vec2 v_texcoord;
out vec4 fragColor;
uniform sampler2D _BaseTexture0;
uniform float image_width;
uniform float image_height;
uniform float adjustable_intensity;
uniform float adjustable_blur_y;

  vec4 blur(vec4 curColor, float blurSize, vec2 uv,float intensity){
    float half_gaussian_weight[9];
    half_gaussian_weight[0]= 0.20;//0.137401;
    half_gaussian_weight[1]= 0.19;//0.125794;
    half_gaussian_weight[2]= 0.17;//0.106483;
    half_gaussian_weight[3]= 0.15;//0.080657;
    half_gaussian_weight[4]= 0.13;//0.054670;
    half_gaussian_weight[5]= 0.11;//0.033159;
    half_gaussian_weight[6]= 0.08;//0.017997;
    half_gaussian_weight[7]= 0.05;//0.008741;
    half_gaussian_weight[8]= 0.02;//0.003799;
      
    vec4 sum            = vec4(0.0);
    vec4 result         = vec4(0.0);
    vec2 unit_uv        = vec2(blurSize/image_width,blurSize/image_height);
    unit_uv = unit_uv * intensity;
    vec4 centerPixel    = curColor*half_gaussian_weight[0];
    float sum_weight    = half_gaussian_weight[0];
    for(int i=1;i<=8;i++)
    {
        vec2 curRightCoordinate = uv+vec2(float(0),float(i))*unit_uv;
        vec2 curLeftCoordinate  = uv+vec2(float(0),float(-i))*unit_uv;
        vec4 rightColor = texture(_BaseTexture0,curRightCoordinate);
        vec4 leftColor = texture(_BaseTexture0,curLeftCoordinate);
        sum+=rightColor*half_gaussian_weight[i];
        sum+=leftColor*half_gaussian_weight[i];
        sum_weight+=half_gaussian_weight[i]*2.0;
    }
    return (sum+centerPixel)/sum_weight;
  }

void main()
{
    vec4 color  =  texture(_BaseTexture0, v_texcoord);
    fragColor = blur(color, 4.8, v_texcoord,adjustable_intensity / 100.0*adjustable_blur_y/100.0);
}




