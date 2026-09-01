in vec3 a_position;
in vec2 a_texcoord0;
out vec2 v_texcoord;
uniform mat4 u_ModelViewProjMat;
void main()
{
    gl_Position = u_ModelViewProjMat * vec4(a_position, 1.0);
    v_texcoord = a_texcoord0;
}
















