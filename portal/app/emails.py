"""E-mail bodies (HTML + plain text) for sign-up confirmation, password reset and welcome.

Table layout with inline styles and bgcolor attributes, because mail clients (Outlook, Gmail) ignore
most CSS. Nothing depends on images: the header is a text wordmark and the icon is decoration only.
Each builder returns (subject, text, html).
"""

from html import escape

BG, CARD, EDGE = "#15130f", "#1f1b14", "#d9a441"
TEXT, MUTED, GOLD, BOX = "#f2e6c9", "#9a8f7c", "#f3d27a", "#2a241a"
FONT = "Arial,Helvetica,sans-serif"


def _p(html, size=15, color=TEXT, mb=14):
    return f'<p style="margin:0 0 {mb}px;font-size:{size}px;line-height:1.55;color:{color}">{html}</p>'


def _button(label, url, primary=True):
    bg, fg = (EDGE, BG) if primary else (BOX, GOLD)
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 8px 6px 0;display:inline-table"><tr>'
        f'<td bgcolor="{bg}" style="border-radius:4px;border:2px solid {EDGE}">'
        f'<a href="{escape(url)}" style="display:block;padding:12px 22px;font:bold 15px {FONT};color:{fg};text-decoration:none">{escape(label)}</a>'
        f"</td></tr></table>"
    )


def _facts(rows):
    cells = "".join(
        f'<tr><td style="padding:5px 0;font-size:13px;color:{MUTED};width:120px">{escape(k)}</td>'
        f'<td style="padding:5px 0;font-size:15px;color:{TEXT};font-weight:bold">{escape(v)}</td></tr>'
        for k, v in rows
    )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{BOX}" '
        f'style="margin:0 0 18px;border-left:4px solid {EDGE}"><tr><td style="padding:10px 16px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cells}</table></td></tr></table>'
    )


def _steps(items):
    rows = "".join(
        f'<tr><td valign="top" style="padding:0 12px 10px 0;font:bold 15px {FONT};color:{GOLD};width:22px">{i}.</td>'
        f'<td style="padding:0 0 10px;font-size:14px;line-height:1.5;color:{TEXT}">{t}</td></tr>'
        for i, t in enumerate(items, 1)
    )
    return f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 14px">{rows}</table>'


def _h2(text):
    return f'<h2 style="margin:22px 0 10px;font-size:16px;color:{GOLD}">{escape(text)}</h2>'


def _layout(base, title, preheader, blocks, footer_note):
    icon = f'<img src="{escape(base)}/static/apple-touch-icon.png" width="44" height="44" alt="" style="vertical-align:middle;border:0;margin-right:10px;image-rendering:pixelated">'
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark light">
<title>{escape(title)}</title></head>
<body style="margin:0;padding:0;background:{BG}" bgcolor="{BG}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{BG}">{escape(preheader)}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{BG}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{CARD}" style="max-width:560px;border:3px solid {EDGE};border-radius:6px;font-family:{FONT}">
<tr><td bgcolor="{EDGE}" style="height:6px;line-height:6px;font-size:0">&nbsp;</td></tr>
<tr><td style="padding:22px 30px 0">{icon}<span style="vertical-align:middle;font:bold 24px {FONT};letter-spacing:2px;color:{GOLD}">VinOT</span></td></tr>
<tr><td style="padding:14px 30px 8px"><h1 style="margin:0 0 16px;font-size:24px;line-height:1.25;color:{GOLD}">{escape(title)}</h1>{"".join(blocks)}</td></tr>
<tr><td style="padding:16px 30px 24px;border-top:1px solid {BOX}">
{_p(footer_note, 12, MUTED, 8)}
{_p(f'<a href="{escape(base)}" style="color:{MUTED}">{escape(base.split("://")[-1])}</a> &middot; Nunca pedimos sua senha por e-mail.', 12, MUTED, 0)}
</td></tr></table></td></tr></table></body></html>"""


def _fallback(url):
    return _p(f'Se o botão não funcionar, copie este link no navegador:<br><span style="word-break:break-all;color:{GOLD}">{escape(url)}</span>', 12, MUTED, 8)


def confirmation(base, url, hours, char=None, voc=None):
    facts = [("Personagem", char)] if char else []
    facts += [("Vocação", voc)] if voc else []
    blocks = [
        _p("Recebemos um cadastro com este e-mail. Falta só confirmar que ele é seu para a conta ser criada."),
        *([_facts(facts)] if facts else []),
        _button("Confirmar meu e-mail", url),
        _p(f"O link vale por <b>{hours} horas</b> e funciona uma vez só.", 13, MUTED, 4),
        _h2("O que acontece depois"),
        _steps([
            "Você já entra logado na sua conta no site." + (" Seu personagem é criado na hora e te espera em Thais." if char else ""),
            f'Baixe o cliente em <a href="{escape(base)}/baixar" style="color:{GOLD}">{escape(base.split("://")[-1])}/baixar</a>.',
            "No jogo, entre com <b>este e-mail</b> e a senha que você escolheu.",
        ]),
        _fallback(url),
    ]
    html_body = _layout(base, "Falta só um passo", "Confirme seu e-mail para criar sua conta no VinOT.", blocks,
                        "Se não foi você que se cadastrou, ignore este e-mail: sem a confirmação nenhuma conta é criada.")
    text = (
        "Falta só um passo para entrar no VinOT!\n\n"
        + (f"Personagem: {char}\n" if char else "") + (f"Vocação: {voc}\n" if voc else "") + ("\n" if facts else "")
        + f"Confirme seu e-mail abrindo o link abaixo (vale por {hours} horas e funciona uma vez só):\n{url}\n\n"
        "Depois: você entra logado no site, baixa o cliente em " + f"{base}/baixar" + " e entra no jogo com este e-mail e a senha que escolheu.\n\n"
        "Se não foi você que se cadastrou, ignore este e-mail: sem a confirmação nenhuma conta é criada."
    )
    return "Confirme sua conta no VinOT", text, html_body


def reset(base, url, minutes):
    blocks = [
        _p("Recebemos um pedido para trocar a senha da sua conta no VinOT. Para criar uma senha nova, use o botão abaixo."),
        _button("Criar nova senha", url),
        _p(f"O link vale por <b>{minutes} minutos</b> e funciona uma vez só. Depois de trocar, a senha antiga deixa de valer.", 13, MUTED, 4),
        _h2("Não foi você?"),
        _p("Ignore este e-mail. Sua senha continua a mesma e ninguém consegue entrar na conta só com ele."),
        _h2("Dica"),
        _p("Use uma senha só do VinOT, que você não usa em mais nenhum site.", 14),
        _fallback(url),
    ]
    html_body = _layout(base, "Vamos trocar sua senha", "Link para criar uma senha nova no VinOT.", blocks,
                        "Você recebeu este e-mail porque alguém pediu a troca de senha para este endereço.")
    text = (
        "Vamos trocar sua senha do VinOT.\n\n"
        f"Para criar uma senha nova, abra o link abaixo (vale por {minutes} minutos e funciona uma vez só):\n{url}\n\n"
        "Não foi você? Ignore este e-mail: sua senha continua a mesma."
    )
    return "Trocar a senha do VinOT", text, html_body


def welcome(base, char=None, voc=None, wiki_url=""):
    facts = [("Login no jogo", "seu e-mail")]
    facts += [("Personagem", char)] if char else []
    facts += [("Vocação", voc)] if voc else []
    wiki = wiki_url or f"{base}/wiki"
    blocks = [
        _p("Sua conta está confirmada. Guarde este e-mail: ele resume como entrar."),
        _facts(facts),
        _h2("Para começar"),
        _steps([
            "Baixe o cliente e instale.",
            "Abra o jogo e entre com <b>o e-mail desta conta</b> e a senha que você escolheu.",
            "Escolha seu personagem e vá explorar Thais." if char else "Escolha seu personagem. Se ainda não criou um, crie em <b>Minha conta</b>.",
        ]),
        _button("Baixar o cliente", f"{base}/baixar"),
        _button("Minha conta", f"{base}/conta", primary=False),
        _h2("Vale conhecer"),
        _steps([
            f'<a href="{escape(wiki)}" style="color:{GOLD}">Wiki</a>: criaturas, itens, magias e mapa.',
            f'<a href="{escape(base)}/vocacoes" style="color:{GOLD}">Vocações</a>: o que cada uma faz melhor.',
            f'<a href="{escape(base)}/ranking" style="color:{GOLD}">Ranking</a>: quem lidera o servidor.',
        ]),
    ]
    html_body = _layout(base, "Bem-vindo ao VinOT!", "Sua conta está confirmada. Veja como entrar no jogo.", blocks,
                        "Você recebeu este e-mail porque confirmou o cadastro neste endereço.")
    text = (
        "Bem-vindo ao VinOT! Sua conta está confirmada.\n\n"
        "Login no jogo: o e-mail desta conta e a senha que você escolheu.\n"
        + (f"Personagem: {char}\n" if char else "") + (f"Vocação: {voc}\n" if voc else "")
        + f"\nBaixar o cliente: {base}/baixar\nMinha conta: {base}/conta\nWiki: {wiki}\nVocações: {base}/vocacoes\nRanking: {base}/ranking\n"
    )
    return "Bem-vindo ao VinOT", text, html_body
