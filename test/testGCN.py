import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import logging
from cocotbext.axi import AxiBus, AxiLiteBus, AxiLiteMaster, AxiRam


class TB(object):
    def __init__(self, dut):
        self.dut = dut
        self.log = logging.getLogger("cocotb_tb")
        self.log.setLevel(logging.WARNING)

        # ap_rst_n is active-low. Set it to reset state before starting bus models.
        self.dut.ap_rst_n.setimmediatevalue(0)

        # Start the clock as a parallel process.
        cocotb.start_soon(Clock(self.dut.ap_clk, 4, units="ns").start())

        # AXI-Lite control master. Pass reset because ap_rst_n is active-low.
        self.axi_master = AxiLiteMaster(
            AxiLiteBus.from_prefix(self.dut, "s_axi_control"),
            self.dut.ap_clk,
            self.dut.ap_rst_n,
            reset_active_level=False,
        )

        # AXI memory model for DUT's m_axi_gmem master port.
        # Increase MEM_SIZE if the DUT accesses addresses beyond this range.
        MEM_SIZE = 2**20
        self.axi_ram = AxiRam(
            AxiBus.from_prefix(self.dut, "m_axi_gmem"),
            self.dut.ap_clk,
            self.dut.ap_rst_n,
            reset_active_level=False,
            size=MEM_SIZE,
        )

        self.init_ram()
        cocotb.start_soon(self.cycle_reset())

    async def cycle_reset(self):
        self.dut.ap_rst_n.value = 0
        await RisingEdge(self.dut.ap_clk)
        await RisingEdge(self.dut.ap_clk)
        await RisingEdge(self.dut.ap_clk)
        await RisingEdge(self.dut.ap_clk)
        self.dut.ap_rst_n.value = 1
        await RisingEdge(self.dut.ap_clk)
        await RisingEdge(self.dut.ap_clk)

    def init_ram(self):
        addr = 0
        with open("ram.txt", "r") as f:
            s = f.read(8)
            while s != "":
                byte_val = int(s[::-1], 2)
                self.axi_ram.write(addr, bytes([byte_val]))
                addr += 1
                s = f.read(8)

    async def launch(self, inst_cnt, b_addr=0x00000000):
        await Timer(20, units="ns")
        await self.axi_master.write_dwords(0x0004, [b_addr], byteorder="little")      # 写基地址
        await self.axi_master.write_dwords(0x0008, [inst_cnt], byteorder="little")   # 写指令数
        await self.axi_master.write_dwords(0x0000, [1], byteorder="little")          # 写启动位 
 

@cocotb.test()
async def my_first_test(dut):
    """Try accessing the design."""
    dut._log.info("Wave dumping is enabled by Makefile WAVES=1; open sim_build/Wrapper.fst after simulation.")
    tb = TB(dut)
    await tb.launch(inst_cnt=6)  # 6 条指令 (4 load + 1 spMM + 1 store)

    # done 标志不可用，用超时等待（仿真日志显示 spMM 在 ~1004ns 写回数据）
    await Timer(1000, units="us")

    # 读取 spMM 自动写回的结果
    # 64×8 int32 输出矩阵 = 512 个值 = 2048 字节
    out_addr = 0x5000
    out_bytes = tb.axi_ram.read(out_addr, 2048)

    import struct
    import numpy as np
    from scipy.sparse import csr_matrix
    actual = list(struct.unpack("<512i", out_bytes))

    # 保存 DUT 实际写回的输出矩阵。
    # actual_result.txt：按 64 行 × 8 列保存，便于直接查看矩阵。
    # actual_result_flat.txt：按一维顺序保存，便于和 flatten 后的 expected 对比。
    actual_mat = np.array(actual, dtype=np.int32).reshape(64, 8)
    np.savetxt("actual_result.txt", actual_mat, fmt="%d")
    np.savetxt("actual_result_flat.txt", np.array(actual, dtype=np.int32), fmt="%d")
    print("Saved DUT output matrix to actual_result.txt")

    # 重新计算期望值 (与 Dram.py 相同参数: seed=0, 64×64 sparse/每行16个非零, 64×8 dense)
    M, K, N, nnz_per_row = 64, 64, 8, 16
    np.random.seed(0)
    I_mat = np.zeros((M, K), dtype=np.int32)
    for r in range(M):
        cols = np.random.choice(K, size=nnz_per_row, replace=False)
        I_mat[r, cols] = np.random.randint(1, 100, size=nnz_per_row)
    W_mat = np.random.randint(1, 100, size=(K, N)).astype(np.int32)
    O_mat = np.matmul(I_mat, W_mat)
    expected = list(O_mat.flatten().astype(np.int32))

    # 可选：同时保存 Python 期望矩阵和差值矩阵，方便定位 mismatch。
    expected_mat = np.array(expected, dtype=np.int32).reshape(M, N)
    diff_mat = actual_mat.astype(np.int64) - expected_mat.astype(np.int64)
    np.savetxt("expected_result.txt", expected_mat, fmt="%d")
    np.savetxt("diff_result.txt", diff_mat, fmt="%d")
    print("Saved expected matrix to expected_result.txt")
    print("Saved actual-expected diff matrix to diff_result.txt")

    print(f"\nExpected ({len(expected)} values): {expected[:8]}...")
    print(f"Actual   ({len(actual)} values):   {actual[:8]}...")
    assert actual == expected, f"Output mismatch!\n  Expected first 8: {expected[:8]}\n  Got first 8:      {actual[:8]}"
    print("✓ PASS: Output matches expected!")

    # 波形由 Makefile 中的 WAVES=1 交给 cocotb/Icarus 自动记录。
    # 仿真结束后打开：gtkwave sim_build/Wrapper.fst
