"""把 0x1346 的 protobuf 收成仓库已经在用的宠物字典。

字段号与 rocom-capture 解析 ZoneGetPetInfoByPageRsp 时用的是同一套：
total_page=2，req_page=3，pet_info=4，version=6。
"""

from __future__ import annotations


def _read_varint(buf: bytes, index: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while index < len(buf) and shift <= 70:
        byte = buf[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, index
        shift += 7
    raise ValueError("varint")


def scan_fields(buf: bytes) -> list[tuple[int, int, object]]:
    """遇到不认识的 wire type 或半截字段就停，后面的 tsf4g 尾不再往下认。"""
    fields: list[tuple[int, int, object]] = []
    index = 0
    size = len(buf)
    while index < size:
        try:
            tag, index = _read_varint(buf, index)
        except ValueError:
            break
        field_no = tag >> 3
        wire = tag & 7
        if field_no == 0:
            break
        try:
            if wire == 0:
                value, index = _read_varint(buf, index)
            elif wire == 2:
                length, index = _read_varint(buf, index)
                if length < 0 or index + length > size:
                    break
                value = buf[index : index + length]
                index += length
            elif wire == 5:
                if index + 4 > size:
                    break
                value = buf[index : index + 4]
                index += 4
            elif wire == 1:
                if index + 8 > size:
                    break
                value = buf[index : index + 8]
                index += 8
            else:
                break
        except ValueError:
            break
        fields.append((field_no, wire, value))
    return fields


def _varints(wire: int, value) -> list[int]:
    if wire == 0 and isinstance(value, int):
        return [value]
    if wire == 2 and isinstance(value, (bytes, bytearray)):
        nums: list[int] = []
        index = 0
        raw = bytes(value)
        while index < len(raw):
            try:
                number, index = _read_varint(raw, index)
            except ValueError:
                break
            nums.append(number)
        return nums
    return []


def _text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.hex()


def _attr_data(blob: bytes) -> dict:
    names = {1: "total_race", 2: "talent", 3: "base_value", 4: "effort_exp", 5: "effort_lv", 6: "effort_add"}
    out: dict[str, int] = {}
    for field_no, wire, value in scan_fields(blob):
        if wire == 0 and field_no in names and isinstance(value, int):
            out[names[field_no]] = value
    return out


def _skill(blob: bytes) -> dict:
    item: dict = {}
    for field_no, wire, value in scan_fields(blob):
        if wire != 0 or not isinstance(value, int):
            continue
        if field_no == 1:
            item["id"] = value
        elif field_no == 3:
            item["is_learned"] = bool(value)
        elif field_no == 4:
            item["is_equipped"] = bool(value)
        elif field_no == 5:
            item["pos"] = value
    return item


def _pet(blob: bytes) -> dict:
    pet: dict = {}
    types: list[int] = []
    skills: list[dict] = []
    attrs: dict[str, dict] = {}
    attr_names = {1: "hp", 2: "attack", 3: "special_attack", 4: "defense", 5: "special_defense", 6: "speed"}
    for field_no, wire, value in scan_fields(blob):
        if field_no == 1 and wire == 0:
            pet["gid"] = value
        elif field_no == 2 and wire == 0:
            pet["conf_id"] = value
        elif field_no == 3 and wire == 2 and isinstance(value, (bytes, bytearray)):
            pet["name"] = _text(bytes(value))
        elif field_no == 6:
            types.extend(_varints(wire, value))
        elif field_no == 7 and wire == 0:
            pet["nature"] = value
        elif field_no == 8 and wire == 0:
            pet["gender"] = value
        elif field_no == 10 and wire == 0:
            pet["level"] = value
        elif field_no == 11 and wire == 0:
            pet["ball_id"] = value
        elif field_no == 12 and wire == 2 and isinstance(value, (bytes, bytearray)):
            for sub_no, sub_wire, sub_val in scan_fields(bytes(value)):
                if sub_no == 1 and sub_wire == 2 and isinstance(sub_val, (bytes, bytearray)):
                    skills.append(_skill(bytes(sub_val)))
        elif field_no == 14 and wire == 2 and isinstance(value, (bytes, bytearray)):
            for sub_no, sub_wire, sub_val in scan_fields(bytes(value)):
                if sub_wire == 2 and sub_no in attr_names and isinstance(sub_val, (bytes, bytearray)):
                    attrs[attr_names[sub_no]] = _attr_data(bytes(sub_val))
        elif field_no == 15 and wire == 0:
            pet["base_conf_id"] = value
        elif field_no == 26 and wire == 0:
            pet["height"] = value
        elif field_no == 27 and wire == 0:
            pet["weight"] = value
        elif field_no == 45 and wire == 0:
            pet["mutation_type"] = value
        elif field_no == 47 and wire == 0:
            pet["blood_id"] = value
        elif field_no == 55 and wire == 0:
            pet["talent_rank"] = value
        elif field_no == 73 and wire == 0:
            pet["wear_medal_conf_id"] = value
        elif field_no == 82 and wire == 0:
            pet["speciality_id"] = value
    if types:
        pet["skill_dam_type"] = types
    if skills:
        pet["skill"] = {"skill_data": skills}
    if attrs:
        pet["attribute_info"] = attrs
    return pet


def parse_pet_list(body: bytes) -> dict:
    """ZoneGetPetInfoByPageRsp。pet_info 里是 repeated PetData。"""
    decoded: dict = {"pet_info": {"pet_data": []}}
    if not body:
        return decoded
    for field_no, wire, value in scan_fields(body):
        if wire == 0 and isinstance(value, int):
            if field_no == 2:
                decoded["total_page"] = value
            elif field_no == 3:
                decoded["req_page"] = value
            elif field_no == 5:
                decoded["page_num"] = value
            elif field_no == 6:
                decoded["version"] = value
        elif field_no == 4 and wire == 2 and isinstance(value, (bytes, bytearray)):
            for sub_no, sub_wire, sub_val in scan_fields(bytes(value)):
                if sub_no == 1 and sub_wire == 2 and isinstance(sub_val, (bytes, bytearray)):
                    decoded["pet_info"]["pet_data"].append(_pet(bytes(sub_val)))
    return decoded
