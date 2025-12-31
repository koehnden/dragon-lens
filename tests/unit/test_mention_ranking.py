import pytest


@pytest.mark.parametrize(
    "text,variants,expected",
    [
        (
            "- 奔驰GLE性能很好\n- 宝马X5也不错\n- 奥迪Q7配置高",
            [["奔驰"], ["宝马"], ["奥迪"]],
            [1, 2, 3],
        ),
        (
            "奔驰GLE性能很好，宝马X5也不错，奥迪Q7配置高。",
            [["奔驰"], ["宝马"], ["奥迪"]],
            [1, 2, 3],
        ),
        (
            "1. benz售后一般\n2. 宝马操控出色",
            [["奔驰", "benz"], ["宝马"]],
            [1, 2],
        ),
        (
            "\n".join([f"- 项目{i}" for i in range(1, 12)]) + "\n- 奔驰",
            [["奔驰"]],
            [10],
        ),
        (
            "没有提到任何品牌",
            [["奔驰"], ["宝马"]],
            [None, None],
        ),
    ],
)
def test_rank_entities(text, variants, expected):
    from services.mention_ranking import rank_entities

    assert rank_entities(text, variants) == expected


def test_rank_entities_list_item_shared_rank():
    from services.mention_ranking import rank_entities

    text = "1. 奔驰和宝马都不错\n2. 奥迪也可以"
    ranks = rank_entities(text, [["奔驰"], ["宝马"], ["奥迪"]])
    assert ranks == [1, 1, 2]

