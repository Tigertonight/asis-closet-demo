const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const code=source.slice(source.indexOf('  function openPhotoUpload()'),source.indexOf('  async function requireTryonAccess('));
test('picker stays inside active modal; cancelling can reopen it and dialog replacement preserves input',()=>{
 const calls=[],input={value:'previous.jpg',click(){assert.equal(this.parent,sheet);assert.equal(sheet.open,true);calls.push('picker');}};
 const sheet={open:true,dataset:{},classList:{remove(){}},contains(x){return x.parent===this},appendChild(x){x.parent=this},set innerHTML(s){assert.notEqual(input.parent,this);this.html=s},showModal(){this.open=true}};
 const body={appendChild(x){x.parent=this}};input.parent=body;
 const ctx=vm.createContext({$:id=>id==='#sheet'?sheet:input,document:{body},esc:String});vm.runInContext(code,ctx);
 vm.runInContext('openPhotoUpload()',ctx);assert.equal(input.value,'');assert.match(sheet.html,/选择照片/);assert.match(sheet.html,/data-action="upload-photo"/);
 vm.runInContext('openPhotoUpload()',ctx);assert.equal(calls.length,2);
 vm.runInContext("modal('其他弹窗','内容')",ctx);assert.equal(input.parent,body);
 assert.match(source,/case "upload-photo":\s+openPhotoUpload\(\)/);
});
