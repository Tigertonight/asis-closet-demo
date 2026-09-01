
in vec3 a_position;
in vec2 a_texcoord0;
out vec2 v_texcoord;
 
 void main()
  {
        v_texcoord  = a_texcoord0;
        gl_Position = vec4(a_position, 1.0);
 }
