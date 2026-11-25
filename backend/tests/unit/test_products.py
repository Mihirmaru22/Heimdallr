

def test_a_name_that_is_a_common_english_word_is_not_a_mention_on_its_own():
    from app.evidence.products import product_for

    vault = product_for("Veeva Vault", ["Vault", "Veeva Vault QMS"])
    assert "Vault" not in vault.names
    assert not vault.mentioned_in("Neptune Energy rolled out Vault Platform for speak-up reports.")
    assert vault.mentioned_in("Kemwell BioPharma implemented Veeva Vault QMS.")
    assert "Windchill" in product_for("PTC Windchill", ["Windchill"]).names  # a coined name still counts alone
    assert product_for("Epic").names == ["Epic"]  # the only name given is kept, common or not
