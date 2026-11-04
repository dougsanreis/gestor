# Laboratório SYRA: login e limite de tentativas

A avaliação foi realizada em cópia local, com banco recém-criado e contas de
exemplo. Nenhuma invasão é inferida do uso das credenciais de demonstração.
Na baseline 6055d327cd74bae571a9c8c19040322a2c3fae24, seis senhas erradas
consecutivas receberam 401 e, logo depois, a senha válida recebeu 200. O teste
só comprova o comportamento observado nas primeiras seis tentativas.

A correção responde 429 a partir da sexta tentativa, em janela de 60 segundos,
e informa Retry-After. Um acesso válido durante o bloqueio também é recusado;
após expirar a janela, o login legítimo volta a funcionar. Os resultados acima descrevem a baseline R1. Na R2, os contadores são persistidos em SQLite e compartilhados por processos no mesmo host que abram o mesmo arquivo; são limitados a 2048 endereços e X-Forwarded-For não é confiado. Um endereço compartilhado pode bloquear usuários legítimos. Uso em rede ou produção requer avaliação de armazenamento, topologia e controles apropriados.

Para reproduzir somente em instância autorizada de laboratório: execute
`node --disable-warning=ExperimentalWarning --test 'tests/*.test.js'`. O teste
cria servidor em loopback e banco em memória, e inclui limitação, cabeçalho
forjado e expiração. Não rodar contra sistemas reais. A proteção foi implementada
neste aplicativo; a ferramenta SYRA Shield é auxiliar de teste e não intercepta
nem bloqueia requisições do Gestor.
