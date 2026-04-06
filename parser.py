import re

def parse_item_text(text: str) -> dict:
    """Extrai informações do item a partir do texto."""
    if not text:
        text = ""
        
    text_lower = text.lower()
    
    # Defaults
    tipo = "Consumo"
    descricao = text
    quantidade = 1
    patrimonio = None
    local = None
    
    # 1. Tipo
    if "permanente" in text_lower:
        tipo = "Permanente"
    elif "consumo" in text_lower:
        tipo = "Consumo"
        
    # 2. Patrimônio
    pat_match = re.search(r'patrim[ôo]nio[\s:]*(?:n[ºo]?\s*)?(\d+)', text_lower)
    if pat_match:
        patrimonio = pat_match.group(1)
        descricao = re.sub(r'patrim[ôo]nio[\s:]*(?:n[ºo]?\s*)?\d+', '', descricao, flags=re.IGNORECASE).strip(' ,;')

    # 3. Local
    loc_match = re.search(r'(laborat[óo]rio|lab|paiol)[\s:]*([\w\d]+)', text_lower)
    if loc_match:
        loc_type = loc_match.group(1)
        loc_num = loc_match.group(2)
        if loc_type.startswith('lab') or loc_type.startswith('laborat'):
            local = f"Laboratório {loc_num.upper()}"
        else:
            local = f"Paiol {loc_num.upper()}"
        descricao = re.sub(r'(laborat[óo]rio|lab|paiol)[\s:]*[\w\d]+', '', descricao, flags=re.IGNORECASE).strip(' ,;')

    # 4. Quantidade
    qtd_match = re.search(r'\b(\d+)\s*(?:unidades?|un|peças?|pcs?)\b', text_lower)
    if not qtd_match:
        qtd_match = re.search(r'^\s*(\d+)\s+', text_lower)
    if qtd_match:
        quantidade = int(qtd_match.group(1))
        # only replace first occurrence to avoid removing random numbers in description
        descricao = descricao.replace(qtd_match.group(0), '', 1).strip(' ,;')
        
    # Clean description
    descricao = re.sub(r'permanente|consumo', '', descricao, flags=re.IGNORECASE)
    descricao = re.sub(r'^[,\s\-]+|[,\s\-]+$', '', descricao)
    
    if not descricao:
        descricao = "Item Desconhecido"
    else:
        descricao = descricao[0].upper() + descricao[1:]
        
    return {
        "tipo": tipo,
        "descricao": descricao,
        "quantidade": quantidade,
        "patrimonio": patrimonio,
        "local": local
    }
