import unittest

from backend.main import BreedCalculator, _calc_nature_prob, compute_species_recommendations


def _pet(serial, **overrides):
    pet = {
        "serial_num": serial,
        "mutation": 0,
        "talent_skill": 0,
        "gender": 1,
        "nature": 0,
        "talent_rank": 1,
        "height": 100,
        "weight": 1000,
        "base_height_low": 80,
        "base_height_high": 120,
        "base_weight_low": 500,
        "base_weight_high": 1500,
    }
    for stat in ("hp", "adAttack", "apAttack", "adDefense", "apDefense", "speed"):
        pet[f"{stat}_talent"] = 0
    pet.update(overrides)
    return pet


class ReleaseAndBreedTests(unittest.TestCase):
    def test_breed_weights_favor_stats_both_parents_have(self):
        calc = BreedCalculator(["hp", "speed"], ["hp", "speed"])
        self.assertEqual(calc.weights["hp"], 700)
        self.assertEqual(calc.weights["speed"], 700)
        self.assertEqual(calc.weights["adAttack"], 100)
        self.assertAlmostEqual(calc.prob2, 0.875)
        self.assertAlmostEqual(calc.prob3, 0.125)
        both = calc.get_target_prob(["hp", "speed"])
        other = calc.get_target_prob(["adAttack"])
        self.assertGreater(both, other)

    def test_king_ball_requires_its_stat(self):
        calc = BreedCalculator(["hp"], ["hp"], king_ball_attr="speed")
        self.assertEqual(calc.get_target_prob(["adAttack"]), 0)
        self.assertGreater(calc.get_target_prob(["speed", "hp"]), 0)

    def test_nature_adds_both_parents_then_a_random_share(self):
        probability = _calc_nature_prob({"nature": 2}, {"nature": 2}, 2, 25)
        self.assertAlmostEqual(probability, 0.7 + 0.3 / 25)

    def test_release_keeps_mutations_mercy_best_specialists_and_top_score(self):
        pets = [
            _pet(1, mutation=1),
            _pet(2, talent_skill=50001),
            _pet(3, talent_skill=402, speed_talent=30),
            _pet(4, talent_skill=402, speed_talent=5),
            _pet(5, gender=2, height=110, weight=2000),
            _pet(6, gender=2, height=90, weight=600),
            _pet(7, talent_rank=4, hp_talent=31),
            _pet(8),
            _pet(9),
            _pet(10, mutation=32),
        ]
        result = compute_species_recommendations(pets, {}, keep_count=1)
        kept = set(result["kept_serials"])
        recommended = set(result["recommended_serials"])
        self.assertTrue({1, 2, 3, 5, 7} <= kept)
        self.assertTrue({4, 6, 8, 9, 10} <= recommended)
        self.assertNotIn(10, kept)


if __name__ == "__main__":
    unittest.main()
