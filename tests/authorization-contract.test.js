import {test} from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {openDatabase} from '../src/db.js';
import {seedDatabase} from '../src/seed.js';
import {createApp} from '../src/app.js';

test('autorização por papel, alterações negadas e dados compartilhados',async()=>{
  const db=openDatabase(':memory:');seedDatabase(db,{days:1});
  const app=createApp({db,publicDir:path.resolve('public'),logger:{log(){},error(){}}});
  await new Promise(r=>app.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${app.address().port}`;
  async function call(method,url,body,token){const r=await fetch(base+url,{method,headers:{...(body?{'content-type':'application/json'}:{}),...(token?{authorization:`Bearer ${token}`}:{})},body:body?JSON.stringify(body):undefined});let data;try{data=await r.json()}catch{}return {status:r.status,data};}
  try {
    for(const [m,p,b] of [['GET','/api/clients'],['POST','/api/clients',{name:'anonymous'}],['DELETE','/api/clients/1'],['GET','/api/reports/campaigns.csv']]) assert.equal((await call(m,p,b)).status,401);
    const admin=(await call('POST','/api/auth/login',{email:'admin@gestor.local',password:'admin123'})).data.token;
    const manager=(await call('POST','/api/auth/login',{email:'gestor@gestor.local',password:'gestor123'})).data.token;
    const before=(await call('GET','/api/users',null,admin)).data;
    assert.equal((await call('GET','/api/users',null,manager)).status,403);
    assert.equal((await call('POST','/api/users',{name:'Synthetic Person',email:'person@lab.invalid',password:'only-synthetic',role:'admin'},manager)).status,403);
    assert.equal((await call('DELETE','/api/users/1',null,manager)).status,403);
    assert.equal((await call('PUT','/api/users/2',{role:'admin',is_admin:true},manager)).status,405);
    assert.deepEqual((await call('GET','/api/users',null,admin)).data,before);
    const first=await call('POST','/api/clients',{name:'Synthetic Alpha'},admin);
    const second=await call('POST','/api/clients',{name:'Synthetic Beta'},manager);
    assert.equal(first.status,201);assert.equal(second.status,201);
    const updated=await call('PUT',`/api/clients/${first.data.id}`,{id:second.data.id,name:'Updated Alpha',role:'admin',is_admin:true},manager);
    assert.equal(updated.status,200);assert.equal(updated.data.id,first.data.id);
    assert.equal(updated.data.role,undefined);assert.equal(updated.data.is_admin,undefined);
    assert.equal((await call('GET',`/api/clients/${second.data.id}`,null,admin)).data.name,'Synthetic Beta');
    assert.equal((await call('GET','/api/reports/campaigns.csv',null,manager)).status,200);
    assert.equal((await call('POST','/api/auth/logout',null,manager)).status,204);
    assert.equal((await call('DELETE',`/api/clients/${first.data.id}`,null,manager)).status,401);
    assert.equal((await call('GET',`/api/clients/${first.data.id}`,null,admin)).status,200);
    assert.equal((await call('DELETE',`/api/clients/${first.data.id}`,null,admin)).status,204);
  } finally {await new Promise(r=>app.close(r));db.close();}
});
