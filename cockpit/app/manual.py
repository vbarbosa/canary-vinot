"""Manual: the game's commands (read from the datapack's TalkActions) with a short how-to, and a guide to the panel.

Commands found in the datapack but missing from the lists below still show up, as "sem descrição", so the page never
falls behind the scripts.
"""

import glob
import os
import re
from functools import lru_cache

from . import places

TALK = re.compile(r"(\w+)\s*=\s*TalkAction\(([^)]*)\)")

# word -> (usage, what it does, topic)
PLAYER = {
    "!commands": ("!commands", "Lista os comandos que o seu personagem pode usar.", "Geral"),
    "!online": ("!online", "Quem está online, quantos treinando e quantos parados.", "Geral"),
    "!serverinfo": ("!serverinfo", "Rates do servidor (XP, skill, magia, loot).", "Geral"),
    "!time": ("!time", "Hora do Tibia (dia ou noite) e a hora real.", "Geral"),
    "!position": ("!position", "Mostra a sua posição no mapa (x, y, andar).", "Geral"),
    "!emote": ("!emote on / !emote off", "Mostra as magias como emote (texto laranja) em vez de fala.", "Geral"),
    "!balance": ("!balance", "Saldo do banco.", "Banco"),
    "!deposit": ("!deposit valor / !deposit all", "Guarda gold no banco.", "Banco"),
    "!withdraw": ("!withdraw valor", "Tira gold do banco.", "Banco"),
    "!transfer": ("!transfer valor, nome", "Transfere gold do banco para outro jogador.", "Banco"),
    "!bless": ("!bless", "Compra todas as bênçãos de uma vez.", "Loja"),
    "!aol": ("!aol", "Compra um amulet of loss.", "Loja"),
    "!refill": ("!refill", "Recarrega anéis e amuletos com silver tokens.", "Loja"),
    "!flask": ("!flask on / !flask off", "Liga ou desliga receber os frascos vazios das poções.", "Loja"),
    "!hiddenshop": ("!hiddenshop on / off", "Esconde da lista de venda dos NPCs os itens que você está usando.", "Loja"),
    "!reward": ("!reward", "Escolhe a arma de exercício de presente (uma vez por personagem).", "Loja"),
    "!autoloot": ("!autoloot", "Ajustes do autoloot (quando liberado).", "Loot"),
    "!checkvip": ("!vip", "Mostra o tempo de VIP da conta.", "Conta"),
    "!buyhouse": ("!buyhouse", "Compra a casa olhando para a porta, pelo banco. Preço e nível mínimo na Imobiliária do painel.", "Casas"),
    "!sellhouse": ("!sellhouse nome", "Dentro da sua casa, abre a troca da casa com outro jogador.", "Casas"),
    "!leavehouse": ("!leavehouse", "Dentro da sua casa, devolve ela (os itens vão para o depot).", "Casas"),
    "!leilao": ("!leilao", "Lista os leilões de casa abertos, com número, maior lance e quanto falta.", "Casas"),
    "!lance": ("!lance nº valor", "Dá um lance num leilão (ex.: !lance 3 50000). O banco precisa cobrir; paga só se ganhar.", "Casas"),
    "!roleta": ("!roleta", "Gira a roleta da sorte: giros grátis por dia, depois giro extra ou gold do banco.", "Diversão"),
    "!evento": ("!evento / !evento sair", "Entra (ou sai) da inscrição do evento aberto pelo Mestre.", "Eventos"),
    "!bola": ("!bola", "No evento Bolas de neve: joga uma bola na direção em que você olha.", "Eventos"),
    "!r": ("!r resposta", "No Quiz: responde a pergunta da vez. Acento e maiúscula não importam.", "Eventos"),
    "!checktaint": ("!checktaint", "Quest Soul War: mostra o seu nível de taint.", "Quests"),
}

STAFF = {
    "/i": ("/i item, quantidade", "Cria um item (nome ou número)."),
    "/goto": ("/goto nome", "Vai até um jogador, monstro ou NPC."),
    "/t": ("/t nome", "Manda o jogador para o templo dele."),
    "/c": ("/c nome", "Puxa o jogador até você."),
    "/a": ("/a número", "Anda N sqm na direção em que você olha (atravessa parede)."),
    "/up": ("/up", "Sobe um andar."),
    "/down": ("/down", "Desce um andar."),
    "/town": ("/town cidade", "Vai para o templo de uma cidade."),
    "/pos": ("/pos x, y, z", "Sem parâmetro mostra a posição; com x, y, z vai até lá."),
    "/m": ("/m monstro", "Cria um monstro na sua frente."),
    "/s": ("/s monstro", "Cria um monstro que é seu summon."),
    "/n": ("/n npc", "Cria um NPC."),
    "/r": ("/r", "Remove o que está na sua frente."),
    "/b": ("/b mensagem", "Anuncia para todo mundo."),
    "/ghost": ("/ghost", "Fica invisível para os jogadores."),
    "/kick": ("/kick nome", "Desconecta o jogador."),
    "/ban": ("/ban nome, dias, motivo", "Bane a conta."),
    "/unban": ("/unban nome", "Tira o banimento."),
    "/info": ("/info nome", "Dados do jogador (IP, conta, posição)."),
    "/clean": ("/clean", "Limpa os itens soltos no chão do mapa."),
    "/save": ("/save", "Salva o jogo agora."),
    "/raid": ("/raid nome", "Solta uma raid."),
    "/listraid": ("/listraid", "Lista as raids e as chances."),
    "/owner": ("/owner nome", "Olhando a porta, passa a casa para alguém."),
    "/gotohouse": ("/gotohouse casa", "Vai até a porta de uma casa."),
    "/addmoney": ("/addmoney nome, valor", "Dá gold para o jogador."),
    "/addskill": ("/addskill nome, skill, quantidade", "Sobe skill ou level."),
    "/addoutfit": ("/addoutfit nome, looktype", "Libera um outfit."),
    "/addmount": ("/addmount nome, id", "Libera uma montaria."),
    "/reload": ("/reload tipo", "Recarrega uma parte do servidor (config, scripts, monstros...)."),
    "/closeserver": ("/closeserver", "Fecha o servidor para jogadores."),
    "/openserver": ("/openserver", "Abre o servidor."),
    "/looktype": ("/looktype número", "Muda a sua aparência."),
    "/getlook": ("/getlook", "Mostra o outfit de quem está na sua frente."),
    "/countmonsters": ("/countmonsters", "Conta os monstros do mapa."),
    "/spy": ("/spy nome", "Vê o inventário do jogador."),
}

# How to use each screen of the panel, by its menu path. The menu itself (sections, names, order) comes from
# main.MENU; tools/check_contracts.py fails when a menu screen has no text here.
HOWTO = {
    "/": "Quem está online, saúde do servidor, próximas tarefas da Agenda e atalhos.",
    "/ranking": "Hall da fama: level, skills, magia, gold e mortes, por vocação.",
    "/historico": "Tudo que o painel fez, com quem clicou e o resultado no jogo.",
    "/manual": "Esta página.",
    "/turma": "Os amigos fixos. Marque quem é da turma para dar presentes e levar para eventos de uma vez.",
    "/teleporte": "Leva jogadores (ou a turma) para templos, NPCs, hunts, casas e lugares salvos. O filtro Criaturas mostra onde cada monstro nasce.",
    "/raids": "Soltar agora: escolha a invasão e clique. Automáticas: ligue ou desligue cada raid, mude a chance por minuto e o mínimo de jogadores; a agenda semanal fica na Agenda.",
    "/eventos": "Mini-games (Zombie, Bolas de neve, Capture a bandeira, Battlefield, Quiz). Escolha a arena, quem joga e o prêmio. Salve como evento pronto para agendar; com inscrição, a galera entra com !evento.",
    "/roleta": "Prêmios, pesos (chance), giros grátis por dia, preço do giro e onde fica a roleta. Dá giros extras para alguém.",
    "/boosted": "Escolhe a criatura e o boss em destaque no lugar do sorteio. Vale no próximo início do jogo.",
    "/metin": "Pedra Metin: tipos (vida, ondas de monstros, loot), lugares onde soltar, soltar agora, placar de dano e histórico das pedras já destruídas.",
    "/agenda": "Tarefas automáticas: salvar, anunciar, limpar o chão, raids, eventos, presentes, abrir e fechar o servidor.",
    "/jogadores": "A ficha de cada personagem: itens, level, skills, outfit, grupo, banir, renomear, troféu do Vinot, giros da roleta.",
    "/contas": "Criar conta e personagem, trocar senha, premium e Tibia coins.",
    "/guilds": "O portal das guilds: criar, membros, cargos, líder, banco, mensagem do dia e guerras.",
    "/kits": "Pacotes de itens prontos para dar de uma vez (e para prêmio de eventos).",
    "/economia": "Quanto gold existe e onde: bancos, mochilas, depósitos, guildas, mercado e casas. Também o preço da Tibia coin e a chave Pix da loja do portal.",
    "/pedidos": "Compras de Tibia coins do portal pagas por Pix. Confira o código do pedido no app do banco e confirme para entregar as coins.",
    "/mercado": "Ofertas abertas no mercado do jogo e os últimos negócios. Cancelar devolve os itens ou o gold.",
    "/imobiliaria": "As casas do mapa: dar, vender, despejar, aluguel, preço de venda no jogo e leilões com !lance.",
    "/mundo": "Nome, mensagem do dia, boas-vindas, estátua do Vinot, tipo de PvP, rates e estágios de XP. Aplica sem reiniciar.",
    "/metricas": "CPU, memória, disco e tempo de resposta do jogo, em gráficos de 7 dias.",
    "/logs": "Os logs do servidor e dos comandos de GM, só leitura.",
    "/equipe": "Co-administradores: dê acesso a um amigo e escolha que áreas do painel ele pode usar.",
}


def panel_guide(menu):
    """[(section title, [(path, label, text)])] in menu order."""
    return [(title, [(href, label, HOWTO.get(href, "sem descrição")) for href, _, label in links]) for _, _, title, links in menu]


@lru_cache(maxsize=1)
def scanned():
    """word -> group (normal, gamemaster, god) for every TalkAction in the datapacks."""
    root = os.path.dirname(places.DATAPACK)
    found = {}
    for path in glob.glob(os.path.join(root, "data*", "scripts", "**", "*.lua"), recursive=True):
        if os.path.basename(path).startswith("#"):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for m in TALK.finditer(text):
            g = re.search(re.escape(m.group(1)) + r':groupType\("(\w+)"\)', text)
            for word in re.findall(r'"([^"]+)"', m.group(2)):
                found.setdefault(word, g.group(1) if g else "normal")
    return found


def player_commands():
    words = scanned()
    rows = [dict(word=w, usage=u, text=t, topic=topic) for w, (u, t, topic) in PLAYER.items() if not words or w in words]
    known = set(PLAYER) | {"!vip"}
    rows += [dict(word=w, usage=w, text="sem descrição", topic="Outros") for w, g in sorted(words.items()) if g == "normal" and w not in known]
    return rows


def staff_commands():
    words = scanned()
    rows = [dict(word=w, usage=u, text=t, group=words.get(w, "god")) for w, (u, t) in STAFF.items() if not words or w in words]
    rows += [dict(word=w, usage=w, text="", group=g) for w, g in sorted(words.items()) if g in ("god", "gamemaster") and w not in STAFF and not w.startswith("!")]
    return rows
