# 5. Instalação e Execução Local

## 5.1 Pré-requisitos
- **Node.js 22.13 ou superior** (recomendado: LTS mais recente) — https://nodejs.org
- Git (opcional, para clonar)
- Um navegador moderno

Verifique:
```bash
node -v
```

## 5.2 Passo a passo
```bash
git clone https://github.com/dougsanreis/gestor.git
cd gestor
npm start
```
Não há `npm install`: o projeto não tem dependências.

Abra **http://127.0.0.1:3000** e entre com:
| Perfil | E-mail | Senha |
|---|---|---|
| Administrador | admin@gestor.local | admin123 |
| Gestor | gestor@gestor.local | gestor123 |

Na primeira execução o banco `data/gestor.db` é criado e populado automaticamente.

## 5.3 Comandos
| Comando | O que faz |
|---|---|
| `npm start` | inicia o servidor |
| `npm run dev` | inicia com recarga automática ao salvar arquivos (`--watch`) |
| `npm run seed` | apaga e recria o banco com os dados de demonstração |
| `npm test` | roda os testes automatizados |

## 5.4 Configuração (variáveis de ambiente)
| Variável | Padrão | Descrição |
|---|---|---|
| `PORT` | `3000` | porta HTTP |
| `HOST` | `127.0.0.1` | só aceita conexões desta máquina. Use `0.0.0.0` para acessar pela rede local (ex.: celular) |
| `DB_PATH` | `data/gestor.db` | caminho do banco |

Linux/macOS:
```bash
PORT=8080 npm start
```
Windows PowerShell:
```powershell
$env:PORT=8080; npm start
```

## 5.5 Solução de problemas
| Sintoma | Causa / solução |
|---|---|
| `No such built-in module: node:sqlite` | Node antigo. Atualize para ≥ 22.13 |
| `EADDRINUSE` | Porta ocupada. Use `PORT=3001 npm start` ou feche o outro processo |
| Login volta para a tela inicial | Token expirou (8h) ou banco foi recriado. Entre novamente |
| Dashboard vazio | As métricas do seed são relativas à data em que o banco foi criado. Rode `npm run seed` |
| Quero começar do zero | `npm run seed` |
