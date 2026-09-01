
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

    void main()
    {
        fragColor =  texture(_BaseTexture0, v_texcoord);
      
    }
