export function validateAssignment(plan,role){
 if(!plan||typeof plan!=='object'||Array.isArray(plan)||Object.keys(plan).sort().join(',')!=='owner,reason'||plan.owner!==role||typeof plan.reason!=='string'||!plan.reason.trim()||plan.reason.length>1024)throw Error('Coordinator assignment does not match host-approved specialist');
 return plan;
}
