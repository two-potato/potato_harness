export const OBJECTIVE='Fix subtotal so it multiplies integer unit price by quantity. Preserve function signature.';
export function trialFixture(request){
 if(request.role!=='backend'||request.model!=='fixture/test'||request.coordination?.objective!==OBJECTIVE||JSON.stringify(request.coordination?.scope)!=='["calculation.py"]')throw Error('FIXTURE_TRIAL_ONLY');
 return (phase,body)=>{
  const content=JSON.stringify(phase==='valera'?{owner:'backend',reason:'synthetic routing'}:{edits:[{path:'calculation.py',content:'def subtotal(unit_cents, quantity):\n    return unit_cents * quantity\n'}],summary:'synthetic trial proposal'});
  const base={id:'potato-fixture',created:1,model:'test'};
  const chunk=(delta,finish_reason,usage)=>'data: '+JSON.stringify({...base,object:'chat.completion.chunk',choices:[{index:0,delta,finish_reason}],...(usage?{usage}:{})})+'\n\n';
  return new Response(chunk({role:'assistant',content},null)+chunk({},'stop',{prompt_tokens:10,completion_tokens:10,total_tokens:20})+'data: [DONE]\n\n',{headers:{'Content-Type':'text/event-stream'}});
 };
}
