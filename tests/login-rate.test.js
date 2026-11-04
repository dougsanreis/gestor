import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { openDatabase } from '../src/db.js';
import { seedDatabase } from '../src/seed.js';
import { createApp } from '../src/app.js';

test('após cinco falhas o endpoint limita e não abre sessão', async () => {
  const db=openDatabase(':memory:'); seedDatabase(db,{days:1});
  let now=100_000;
  const app=createApp({db, publicDir:path.resolve('public'),logger:{log(){},error(){}},loginClock:()=>now});
  await new Promise(resolve=>app.listen(0,'127.0.0.1',resolve));
  try {
    const url=`http://127.0.0.1:${app.address().port}/api/auth/login`;
    async function login(password){return fetch(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({email:'gestor@gestor.local',password})});}
    for(let i=0;i<5;i++) assert.equal((await login('synthetic-wrong')).status,401);
    const blocked=await login('synthetic-wrong');
    assert.equal(blocked.status,429);
    assert.ok(Number(blocked.headers.get('retry-after'))>0);
    assert.equal((await login('gestor123')).status,429);
    const spoofed=await fetch(url,{method:'POST',headers:{'content-type':'application/json','x-forwarded-for':'198.51.100.99'},body:JSON.stringify({email:'gestor@gestor.local',password:'gestor123'})});
    assert.equal(spoofed.status,429);
    now+=60_001;
    assert.equal((await login('gestor123')).status,200);
  } finally { await new Promise(resolve=>app.close(resolve)); db.close(); }
});

test('limitador limita capacidade e remove apenas entradas expiradas', async () => {
  const {LoginLimiter}=await import('../src/login-limit.js');
  const db=openDatabase(':memory:'); let now=1_000;
  const limiter=new LoginLimiter({db,clock:()=>now,windowMs:1000,maxFailures:2,maxClients:1});
  assert.equal(limiter.reserve('127.0.0.1').retryMs,0);
  assert.equal(limiter.reserve('127.0.0.1').retryMs,0);
  assert.ok(limiter.reserve('127.0.0.1').retryMs>0);
  assert.ok(limiter.reserve('127.0.0.2').retryMs>0);
  assert.ok(limiter.reserve(undefined).retryMs>0);
  now+=1001;
  assert.equal(limiter.reserve('127.0.0.2').retryMs,0);
  db.close();
});

test('indisponibilidade do ledger impede login', async () => {
  const db=openDatabase(':memory:'); seedDatabase(db,{days:1});
  const app=createApp({db,publicDir:path.resolve('public'),logger:{log(){},error(){}}});
  await new Promise(resolve=>app.listen(0,'127.0.0.1',resolve));
  db.close();
  try {
    const response=await fetch(`http://127.0.0.1:${app.address().port}/api/auth/login`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({email:'gestor@gestor.local',password:'gestor123'})});
    assert.equal(response.status,503);
  } finally { await new Promise(resolve=>app.close(resolve)); }
});
