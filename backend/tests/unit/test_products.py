

def test_a_name_that_is_a_common_english_word_is_not_a_mention_on_its_own():
    from app.evidence.products import product_for

    vault = product_for("Veeva Vault", ["Vault", "Veeva Vault QMS"])
    assert "Vault" not in vault.names
    assert not vault.mentioned_in("Neptune Energy rolled out Vault Platform for speak-up reports.")
    assert vault.mentioned_in("Kemwell BioPharma implemented Veeva Vault QMS.")
    assert "Windchill" in product_for("PTC Windchill", ["Windchill"]).names  # a coined name still counts alone
    assert product_for("Epic").names == ["Epic"]  # the only name given is kept, common or not


def test_the_typed_name_without_its_makers_word_counts_as_a_mention():
    from app.evidence.products import product_for

    windchill = product_for("PTC Windchill", ["Windchill PLM", "PTC Windchill PLM"])
    assert windchill.mentioned_in("Welbilt Leverages Windchill in the Cloud.")  # PTC's own story never says "PTC"
    assert product_for("Oracle NetSuite").mentioned_in("Lick Home prepares for growth with NetSuite OneWorld.")
    assert "Dynamics 365" in product_for("Microsoft Dynamics 365").names
    assert product_for("Shopify Plus").names == ["Shopify Plus"]  # "Plus" alone is too short to be a name
    assert "Vault" not in product_for("Veeva Vault").names  # a common word, dropped as before
