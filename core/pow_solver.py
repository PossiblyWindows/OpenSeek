import base64
import ctypes
import json
import platform
import struct
from typing import Any, Optional

KECCAK_ROUND_CONSTANTS = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]

KECCAK_ROTATION_OFFSETS = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]


def _build_x86_64_jit_solver() -> Optional[Any]:
    if platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        return None

    machine_code = bytearray()
    machine_code.extend(b"\x53\x55\x57\x56\x41\x54\x41\x55\x41\x56\x41\x57")
    machine_code.extend(b"\x48\x81\xec\xc0\x02\x00\x00")
    machine_code.extend(b"\x49\x89\xcc\x49\x89\xd5\x4d\x89\xc6\x4d\x89\xcf")
    machine_code.extend(b"\x48\x31\xdb")

    loop_start_offset = len(machine_code)
    machine_code.extend(b"\x4c\x39\xfb")
    jg_not_found_index = len(machine_code)
    machine_code.extend(b"\x0f\x8f\x00\x00\x00\x00")

    machine_code.extend(b"\x48\x8d\xbc\x24\xe0\x01\x00\x00\x31\xc0\xb9\x19\x00\x00\x00\xf3\x48\xab")
    machine_code.extend(b"\x48\x8d\xbc\x24\xe0\x01\x00\x00\x4c\x89\xe6\x4c\x89\xe9\xf3\xa4")

    machine_code.extend(b"\x48\x85\xdb")
    jnz_index = len(machine_code)
    machine_code.extend(b"\x75\x00")

    machine_code.extend(b"\xc6\x07\x30\x48\xff\xc7")
    jmp_after_itoa_index = len(machine_code)
    machine_code.extend(b"\xeb\x00")

    non_zero_offset = len(machine_code)
    machine_code[jnz_index + 1] = non_zero_offset - (jnz_index + 2)
    machine_code.extend(b"\x48\x89\xd8\x49\xc7\xc0\x0a\x00\x00\x00\x31\xc9")

    itoa_division_offset = len(machine_code)
    machine_code.extend(b"\x31\xd2\x49\xf7\xf0\x80\xc2\x30\x52\xff\xc1\x48\x85\xc0")
    loop1_relative = itoa_division_offset - (len(machine_code) + 2)
    machine_code.extend(b"\x75" + struct.pack("b", loop1_relative))

    pop_digits_offset = len(machine_code)
    machine_code.extend(b"\x58\x88\x07\x48\xff\xc7\xff\xc9")
    loop2_relative = pop_digits_offset - (len(machine_code) + 2)
    machine_code.extend(b"\x75" + struct.pack("b", loop2_relative))

    after_itoa_offset = len(machine_code)
    machine_code[jmp_after_itoa_index + 1] = after_itoa_offset - (jmp_after_itoa_index + 2)

    machine_code.extend(b"\xc6\x07\x06")
    machine_code.extend(b"\xc6\x84\x24\x67\x02\x00\x00\x80")
    machine_code.extend(b"\x48\x8d\xb4\x24\xe0\x01\x00\x00\x48\x89\xe7\xb9\x19\x00\x00\x00\xf3\x48\xa5")

    for round_index in range(1, 24):
        for x in range(5):
            machine_code.extend(b"\x48\x8b\x84\x24" + struct.pack("<I", x * 8))
            for y in range(1, 5):
                machine_code.extend(b"\x48\x33\x84\x24" + struct.pack("<I", (x + 5 * y) * 8))
            machine_code.extend(b"\x48\x89\x84\x24" + struct.pack("<I", 400 + x * 8))

        for x in range(5):
            machine_code.extend(b"\x48\x8b\x84\x24" + struct.pack("<I", 400 + ((x + 1) % 5) * 8))
            machine_code.extend(b"\x48\xd1\xc0")
            machine_code.extend(b"\x48\x33\x84\x24" + struct.pack("<I", 400 + ((x + 4) % 5) * 8))
            machine_code.extend(b"\x48\x89\x84\x24" + struct.pack("<I", 440 + x * 8))

        for x in range(5):
            machine_code.extend(b"\x48\x8b\x94\x24" + struct.pack("<I", 440 + x * 8))
            for y in range(5):
                machine_code.extend(b"\x48\x31\x94\x24" + struct.pack("<I", (x + 5 * y) * 8))

        for x in range(5):
            for y in range(5):
                rot = KECCAK_ROTATION_OFFSETS[x][y]
                machine_code.extend(b"\x48\x8b\x84\x24" + struct.pack("<I", (x + 5 * y) * 8))
                if rot != 0:
                    machine_code.extend(b"\x48\xc1\xc0" + bytes([rot]))
                dest_index = y + 5 * ((2 * x + 3 * y) % 5)
                machine_code.extend(b"\x48\x89\x84\x24" + struct.pack("<I", 200 + dest_index * 8))

        for y in range(5):
            for x in range(5):
                machine_code.extend(b"\x48\x8b\x84\x24" + struct.pack("<I", 200 + (((x + 1) % 5) + 5 * y) * 8))
                machine_code.extend(b"\x48\xf7\xd0")
                machine_code.extend(b"\x48\x23\x84\x24" + struct.pack("<I", 200 + (((x + 2) % 5) + 5 * y) * 8))
                machine_code.extend(b"\x48\x33\x84\x24" + struct.pack("<I", 200 + (x + 5 * y) * 8))
                machine_code.extend(b"\x48\x89\x84\x24" + struct.pack("<I", (x + 5 * y) * 8))

        machine_code.extend(b"\x48\xb8" + struct.pack("<Q", KECCAK_ROUND_CONSTANTS[round_index]))
        machine_code.extend(b"\x48\x31\x04\x24")

    machine_code.extend(b"\x48\x8b\x04\x24\x49\x3b\x06")
    jne1_idx = len(machine_code)
    machine_code.extend(b"\x0f\x85\x00\x00\x00\x00")

    machine_code.extend(b"\x48\x8b\x44\x24\x08\x49\x3b\x46\x08")
    jne2_idx = len(machine_code)
    machine_code.extend(b"\x0f\x85\x00\x00\x00\x00")

    machine_code.extend(b"\x48\x8b\x44\x24\x10\x49\x3b\x46\x10")
    jne3_idx = len(machine_code)
    machine_code.extend(b"\x0f\x85\x00\x00\x00\x00")

    machine_code.extend(b"\x48\x8b\x44\x24\x18\x49\x3b\x46\x18")
    jne4_idx = len(machine_code)
    machine_code.extend(b"\x0f\x85\x00\x00\x00\x00")

    machine_code.extend(b"\x48\x89\xd8")
    jmp_epilogue_idx = len(machine_code)
    machine_code.extend(b"\xe9\x00\x00\x00\x00")

    next_nonce_offset = len(machine_code)
    for jne_idx in [jne1_idx, jne2_idx, jne3_idx, jne4_idx]:
        relative_jump = next_nonce_offset - (jne_idx + 6)
        machine_code[jne_idx + 2: jne_idx + 6] = struct.pack("<i", relative_jump)

    machine_code.extend(b"\x48\xff\xc3")
    loop_jump_offset = loop_start_offset - (len(machine_code) + 5)
    machine_code.extend(b"\xe9" + struct.pack("<i", loop_jump_offset))

    not_found_offset = len(machine_code)
    jg_relative = not_found_offset - (jg_not_found_index + 6)
    machine_code[jg_not_found_index + 2: jg_not_found_index + 6] = struct.pack("<i", jg_relative)
    machine_code.extend(b"\x48\xc7\xc0\xff\xff\xff\xff")

    epilogue_offset = len(machine_code)
    jmp_epilogue_rel = epilogue_offset - (jmp_epilogue_idx + 5)
    machine_code[jmp_epilogue_idx + 1: jmp_epilogue_idx + 5] = struct.pack("<i", jmp_epilogue_rel)

    machine_code.extend(b"\x48\x81\xc4\xc0\x02\x00\x00")
    machine_code.extend(b"\x41\x5f\x41\x5e\x41\x5d\x41\x5c\x5e\x5f\x5d\x5b")
    machine_code.extend(b"\xc3")

    try:
        kernel32 = ctypes.windll.kernel32
        virtual_alloc = kernel32.VirtualAlloc
        virtual_alloc.restype = ctypes.c_void_p
        virtual_alloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong, ctypes.c_ulong]

        memory_address = virtual_alloc(None, len(machine_code), 0x3000, 0x40)
        if not memory_address:
            return None

        ctypes.memmove(memory_address, bytes(machine_code), len(machine_code))
        function_prototype = ctypes.CFUNCTYPE(
            ctypes.c_int64, ctypes.c_char_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64
        )
        return function_prototype(memory_address)
    except Exception:
        return None


_JIT_SOLVER = _build_x86_64_jit_solver()


def _solve_python_fallback(salt: str, expire_at: int, difficulty: int, target_bytes: bytes) -> int:
    def rotate_left_64(val: int, shift: int) -> int:
        return ((val << (shift % 64)) & 0xFFFFFFFFFFFFFFFF) | (val >> ((64 - (shift % 64)) % 64))

    target_words = struct.unpack("<4Q", target_bytes)
    rate_bytes = 136

    for nonce in range(difficulty + 1):
        message = f"{salt}_{expire_at}_{nonce}".encode("utf-8")
        padded = bytearray(message)
        padded.append(0x06)
        while len(padded) % rate_bytes != rate_bytes - 1:
            padded.append(0x00)
        padded.append(0x80)

        state = [[0] * 5 for _ in range(5)]
        for block_start in range(0, len(padded), rate_bytes):
            block = padded[block_start: block_start + rate_bytes]
            words = struct.unpack("<17Q", block)
            for word_index, val in enumerate(words):
                state[word_index % 5][word_index // 5] ^= val

            for round_index in range(1, 24):
                theta_c = [
                    state[x][0] ^ state[x][1] ^ state[x][2] ^ state[x][3] ^ state[x][4]
                    for x in range(5)
                ]
                theta_d = [
                    theta_c[(x - 1) % 5] ^ rotate_left_64(theta_c[(x + 1) % 5], 1)
                    for x in range(5)
                ]
                for x in range(5):
                    for y in range(5):
                        state[x][y] ^= theta_d[x]

                rho_pi_b = [[0] * 5 for _ in range(5)]
                for x in range(5):
                    for y in range(5):
                        rho_pi_b[y][(2 * x + 3 * y) % 5] = rotate_left_64(
                            state[x][y], KECCAK_ROTATION_OFFSETS[x][y]
                        )

                for x in range(5):
                    for y in range(5):
                        state[x][y] = (
                            rho_pi_b[x][y]
                            ^ ((~rho_pi_b[(x + 1) % 5][y]) & rho_pi_b[(x + 2) % 5][y])
                        ) & 0xFFFFFFFFFFFFFFFF

                state[0][0] ^= KECCAK_ROUND_CONSTANTS[round_index]

        if (
            state[0][0] == target_words[0]
            and state[1][0] == target_words[1]
            and state[2][0] == target_words[2]
            and state[3][0] == target_words[3]
        ):
            return nonce

    return 0


def solve_challenge(challenge_data: dict[str, Any]) -> str:
    salt = challenge_data["salt"]
    expire_at = challenge_data["expire_at"]
    difficulty = int(challenge_data.get("difficulty", 144000))
    target_hex = challenge_data["challenge"]
    signature = challenge_data["signature"]
    algorithm = challenge_data.get("algorithm", "DeepSeekHashV1")
    target_path = challenge_data.get("target_path", "/api/v0/chat/completion")

    target_bytes = bytes.fromhex(target_hex)
    prefix_bytes = f"{salt}_{expire_at}_".encode("utf-8")

    nonce: Optional[int] = None

    if _JIT_SOLVER is not None:
        target_buffer = ctypes.create_string_buffer(target_bytes)
        result = _JIT_SOLVER(
            prefix_bytes, len(prefix_bytes), ctypes.byref(target_buffer), difficulty
        )
        if result >= 0:
            nonce = int(result)

    if nonce is None:
        nonce = _solve_python_fallback(salt, expire_at, difficulty, target_bytes)

    solution_payload = {
        "algorithm": algorithm,
        "challenge": target_hex,
        "salt": salt,
        "answer": nonce,
        "signature": signature,
        "target_path": target_path,
    }

    json_serialized = json.dumps(solution_payload, separators=(",", ":"))
    return base64.b64encode(json_serialized.encode("utf-8")).decode("utf-8")
