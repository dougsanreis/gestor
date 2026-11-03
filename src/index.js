// Ponto de entrada: abre o banco, popula na primeira execução e sobe o servidor local.
import { openDatabase } from './db.js';
import { createApp } from './app.js';
import { config } from './config.js';
import { DEMO_USERS, isEmpty, seedDatabase } from './seed.js';

const db = openDatabase(config.dbPath);

if (isEmpty(db)) {
  seedDatabase(db);
  console.log('Primeira execução: banco criado com dados de demonstração.');
}

const server = createApp({ db, publicDir: config.publicDir });

server.listen(config.port, config.host, () => {
  const url = `http://${config.host === '0.0.0.0' ? 'localhost' : config.host}:${config.port}`;
  console.log('\n  Gestor de Anúncios rodando!');
  console.log(`  Interface: ${url}`);
  console.log(`  API:       ${url}/api/health`);
  console.log('  Logins de demonstração:');
  for (const u of DEMO_USERS) console.log(`    ${u.email} / ${u.password} (${u.role})`);
  console.log('\n  Ctrl+C para encerrar.\n');
});

// Encerramento gracioso: fecha conexões e o banco.
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    console.log('\nEncerrando...');
    server.close(() => {
      db.close();
      process.exit(0);
    });
    setTimeout(() => process.exit(0), 3000).unref();
  });
}
