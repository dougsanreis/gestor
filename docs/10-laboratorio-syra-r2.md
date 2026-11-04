# Laboratório SYRA R2: autorização e limites compartilhados

A baseline é `9ff6ad27bd6f4edd00d8898701a4c5b520af79ed`. Este projeto é
um workspace compartilhado: não existe autorização multiempresa. Nenhuma
conclusão de IDOR decorre da leitura dos mesmos clientes por gestor e admin.

| Operação | Anônimo | Gestor | Admin |
|---|---|---|---|
| Clientes, campanhas e métricas: ler, criar, alterar e excluir | 401 | Permitido | Permitido |
| Dashboard e exportação CSV | 401 | Permitido | Permitido |
| Listar/criar/excluir usuários | 401 | 403 | Permitido; não pode excluir a si próprio |
| Alterar o próprio papel por PUT em /api/users/:id | Sem rota | 405 | Sem rota |

As rotas não oferecem alteração de papel. Na verificação, `role` e `is_admin`
extras em um cliente foram ignorados. Um `id` de corpo divergente da URL foi
ignorado e o recurso da URL foi alterado; se uma divergência deveria ser
rejeitada é **POLICY_UNDEFINED**. Recusas administrativas e de sessão revogada
foram seguidas de consulta que confirmou ausência da alteração pretendida.

Na baseline, cinco falhas em um processo não bloquearam a sexta em outro, nem
após reiniciar o primeiro; oito pedidos concorrentes distribuídos produziram
 oito respostas 401. Na candidata, a sexta tentativa no segundo processo e
após reinício retornou 429; oito pedidos concorrentes produziram cinco 401 e
três 429. Ambos processos usaram o mesmo arquivo SQLite sintético. Uma
contenção de escrita devolveu 503, sem autenticar. O limite reserva cada
solicitação antes de verificar a senha: sucesso devolve apenas a própria reserva e não apaga falhas anteriores; falha ou
interrupção a mantém até a expiração. O limite é cinco, janela 60 segundos,
capacidade 2.048 endereços; lotação recusa novas identidades até expiração.
O timeout SQLite é 500 ms. Alterações de relógio, remoção ou substituição do
arquivo de banco e múltiplos hosts não foram qualificados. O limite é por IP
TCP, não por conta; NAT/proxy pode limitar usuários legítimos.

A rede Docker de teste foi criada com `--internal`, sem portas publicadas,
sem modo host, sem socket Docker e sem montar diretório pessoal no alvo. Uma
conexão controlada ao endereço externo 1.1.1.1:443 retornou ENETUNREACH; isso
não comprova todas as possibilidades de conexão ao host ou todos os destinos.
Com a mesma origem IP, outra conta legítima recebeu 429 durante o bloqueio e
200 após 61 segundos reais. Nenhum serviço externo foi utilizado.

A suíte completa executada no laboratório teve 25 testes aprovados. Para
reproduzir em uma rede de laboratório isolada, com Node 22.23.3 ou compatível:
`node --disable-warning=ExperimentalWarning --test 'tests/*.test.js'`.
Os testes criam seus próprios bancos em memória ou temporários. Os testes
entre processos usam dois servidores reais e não substituem o ensaio com 61
segundos reais. A correção está no Gestor; sondas do Shield apenas verificam.
