import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { openDatabase } from '../src/db.js';
import { seedDatabase } from '../src/seed.js';
import { createApp } from '../src/app.js';

for (const kind of ['client','campaign','status']) test(`contrato HTTP de ID: ${kind}`, async () => {
  const db=openDatabase(':memory:'); seedDatabase(db,{days:1});
  const server=createApp({db,publicDir:path.resolve('public'),logger:{log(){},error(){}}});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const base=`http://127.0.0.1:${server.address().port}`;
  async function call(method,url,body,token) {
    const response=await fetch(base+url,{method,headers:{...(body!==undefined?{'content-type':'application/json'}:{}),...(token?{authorization:`Bearer ${token}`}:{})},body:body===undefined?undefined:JSON.stringify(body)});
    let data; try { data=await response.json(); } catch {}
    return {status:response.status,data};
  }
  try {
    const login=async(email,password)=>(await call('POST','/api/auth/login',{email,password})).data.token;
    const admin=await login('admin@gestor.local','admin123');
    const observer=await login('admin@gestor.local','admin123');
    const manager=await login('gestor@gestor.local','gestor123');
    const clientA=(await call('POST','/api/clients',{name:'Synthetic Client A'},admin)).data;
    const clientB=(await call('POST','/api/clients',{name:'Synthetic Client B'},admin)).data;
    let a=clientA,b=clientB,resource='clients',method='PUT',suffix='';
    const campaignBody={client_id:clientA.id,name:'Synthetic Campaign A',platform:'meta'};
    if(kind!=='client') {
      resource='campaigns';
      a=(await call('POST','/api/campaigns',campaignBody,admin)).data;
      b=(await call('POST','/api/campaigns',{...campaignBody,name:'Synthetic Campaign B',client_id:clientB.id},admin)).data;
      if(kind==='status'){method='PATCH';suffix='/status';}
    }
    const url=`/api/${resource}/${a.id}${suffix}`;
    const body=kind==='client'?{name:'Synthetic Changed'}:kind==='campaign'?{...campaignBody,name:'Synthetic Changed'}:{status:'ativa'};
    const read=async id=>{const r=await call('GET',`/api/${resource}/${id}`,undefined,observer);assert.equal(r.status,200);return r.data;};
    const snapshot=async()=>[await read(a.id),await read(b.id)];
    assert.equal((await call(method,url,body,manager)).status,200,'sem id');
    assert.equal((await call(method,url,{...body,id:a.id},manager)).status,200,'id igual');
    const baseline=await snapshot();
    const cases=[b.id,true,false,null,[],{},1.5,Number.MAX_SAFE_INTEGER+1,0,-1,'1','1.0',' 1'];
    const failures=[];
    for(const id of cases){
      const r=await call(method,url,{...body,id,...(kind==='status'?{status:'pausada'}:{name:'Must Not Persist'})},manager);
      const after=await snapshot();
      if(r.status!==422 || JSON.stringify(after)!==JSON.stringify(baseline)) failures.push({id,status:r.status,unchanged:JSON.stringify(after)===JSON.stringify(baseline)});
      if(JSON.stringify(after)!==JSON.stringify(baseline)) await call(method,url,body,manager);
    }
    const prior=await snapshot();
    const anon=await call(method,url,{...body,id:b.id});
    assert.equal(anon.status,401,'autenticação precede validação');
    assert.deepEqual(await snapshot(),prior);
    assert.equal((await call('DELETE','/api/users/1',undefined,manager)).status,403);
    assert.deepEqual(await snapshot(),prior);
    assert.deepEqual(failures,[],`IDs inválidos/divergentes; persistência dos dois registros: ${JSON.stringify(failures)}`);
  } finally {await new Promise(r=>server.close(r));db.close();}
});
