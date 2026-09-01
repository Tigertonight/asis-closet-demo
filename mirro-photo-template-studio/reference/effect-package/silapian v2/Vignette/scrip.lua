local textScript = textScript or {}
textScript.__index = textScript

function textScript.new(constructor, ...)
    local self = setmetatable({}, textScript)
    return self 
end

function textScript:constructor()
end

local function getControlPoints(whiteIntensity, blackIntensity)
    -- initialization, (xw, yw) is white control point, (xb, yb) is black control point
    local xw = 1.0
    local yw = 1.0
    local xb = 0.0
    local yb = 0.0
    local MAX_RANGE = 0.5
    local EPS = 0.005

    -- white control points are located at top or right border
    -- black control points are located at bottom or left border
    if whiteIntensity >= 0.0 then
        xw = 1.0 - whiteIntensity * MAX_RANGE
        yw = 1.0
    else
        xw = 1.0
        yw = 1.0 + whiteIntensity * MAX_RANGE
    end

    if blackIntensity >= 0.0 then
        xb = 0.0
        yb = blackIntensity * MAX_RANGE
    else
        xb = -blackIntensity * MAX_RANGE
        yb = 0.0
    end 

    -- rectify the points
    xw = math.max(xw, EPS)
    yw = math.max(yw, EPS)
    xb = math.min(xb, xw - EPS)
    yb = math.min(yb, yw - EPS)

    return xw, yw, xb, yb
end

local function getLinearCoef(xw, yw, xb, yb)
    local slope = (yw - yb) / (xw - xb)
    local bias = yb - slope * xb
    return slope, bias
end

function textScript:setMaterial(mat, materialIndex)
    
    local filter_renderer = self.parent:GetFilterRenderComponent()
    if filter_renderer == nil then
        print('lua debug info: setMaterialWithFilter-filter_renderer == nil')
        return
    end
    local index = materialIndex - 1 --每个pass都需遍历一遍并且重新设置uniform
    
    local adjustable_white = 0.0
    local adjustable_black = 0.0
    if zs.def_ZS_EDITOR then --pc端
        if mat == nil then
            return
        end
        local pass = mat:GetPass(0)
        if pass == nil then
            return
        end

        local params = pass:_getParams()
        adjustable_white = params["adjustable_x"]:GetFloat()
        adjustable_black = params["adjustable_y"]:GetFloat()
        print('lua debug info: adjustable_x is ', adjustable_white)
        print('lua debug info: adjustable_y is ', adjustable_black)

    else --移动端 
        
        adjustable_white = self.adjustable_x
        adjustable_black = self.adjustable_y
        print('lua debug info: adjustable_x is ', adjustable_white)
        print('lua debug info: adjustable_y is ', adjustable_black)
    end
    adjustable_black = adjustable_black / 100.0*0.32
    adjustable_white = adjustable_white / 100.0
    local xw, yw, xb, yb = getControlPoints(adjustable_white, adjustable_black)
    local slope, bias = getLinearCoef(xw, yw, xb, yb)
    filter_renderer:SetUniform("slope", zs.Variant.new(tonumber(slope)), index)
    filter_renderer:SetUniform("bias", zs.Variant.new(tonumber(bias)), index)
end

function textScript:postUpdate()
    
    local parentSo = self.parent 
    local filterRenderer = parentSo:GetFilterRenderComponent()
    if filterRenderer == nil then
        print("lua--filterRenderer == nil \n")
        return
    end

    local material_count = filterRenderer:GetMaterialCount()
    print('lua debug info: material size is ', material_count)
    if material_count == 0 then
        print('lua debug info:material_count == 0')
        return
    end

    for i = 1, material_count do
        local material = filterRenderer:GetMaterial(i - 1)
        self:setMaterial(material, i)
    end
    
end


return textScript
