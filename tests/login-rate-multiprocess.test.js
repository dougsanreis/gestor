import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import net from 'node:net';

async function freePort() {return new Promise((resolve,reject)=>{const s=net.createServer();s.on('error',reject);s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p));});});}
async function start(dbPath) {
  const port=await freePort();
  const proc=spawn(process.execPath,['--disable-warning=ExperimentalWarning','src/index.js'],{cwd:process.cwd(),stdio:'ignore',env:{PATH:process.env.PATH,HOST:'127.0.0.1',PORT:String(port),DB_PATH:dbPath}});
  const base=`http://127.0.0.1:${port}`;
  for(let i=0;i<60;i++) {if(proc.exitCode!==null)throw Error('LAB_PROCESS_EXITED');try{const r=await fetch(base+'/api/health');if(r.ok)return {proc,base};}catch{} await new Promise(r=>setTimeout(r,50));}
  proc.kill('SIGTERM'); throw Error('LAB_PROCESS_NOT_READY');
}
async function stop(server) {if(server.proc.exitCode!==null)return;await new Promise(resolve=>{server.proc.once('exit',resolve);server.proc.kill('SIGTERM');});}
async function wrong(server) {const r=await fetch(server.base+'/api/auth/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({email:'gestor@gestor.local',password:'incorrect-synthetic'})});return r.status;}

test('dois processos compartilham limite após reinício',async()=>{
  const dir=mkdtempSync(path.join(tmpdir(),'syra-rate-r2-'));const db=path.join(dir,'lab.db');let a,b;
  try {
    a=await start(db);b=await start(db);
    for(let i=0;i<5;i++)assert.equal(await wrong(a),401);
    assert.equal(await wrong(b),429);
    await stop(a);a=await start(db);
    assert.equal(await wrong(a),429);
  } finally {if(a)await stop(a);if(b)await stop(b);rmSync(dir,{recursive:true,force:true});}
});

test('reserva transacional limita oito pedidos concorrentes entre dois processos',async()=>{
  const dir=mkdtempSync(path.join(tmpdir(),'syra-rate-r2-'));const db=path.join(dir,'lab.db');let a,b;
  try {
    a=await start(db);b=await start(db);
    const statuses=await Promise.all(Array.from({length:8},(_,i)=>wrong(i%2?a:b)));
    assert.equal(statuses.filter(s=>s===401).length,5);
    assert.equal(statuses.filter(s=>s===429).length,3);
  } finally {if(a)await stop(a);if(b)await stop(b);rmSync(dir,{recursive:true,force:true});}
});
