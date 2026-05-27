from numpy import binary_repr
import numpy as np
import logging
from inst import inst
from scipy.sparse import csr_matrix

# 固定参数，确保每个数据段 ≤ 4096 字节不跨越 AXI 4KB 边界
M_SPARSE = 64        # 稀疏矩阵行数
K_SPARSE = 64        # 稀疏矩阵列数
N_DENSE  = 8         # 稠密矩阵列数，必须匹配硬件 nColInDense=8
NNZ_PER_ROW = 16     # 每行非零元素数

class data:       
    ### Generates data for GCN-Accelerator
    def __init__(self):
        logging.debug("Data generator created")
    def matrixToBinary(self, A):
        string_A = ''
        for i in A:
            for j in i:
                string_A = string_A + binary_repr(j, 32)[::-1]
        return string_A

    def arrayToBinary(self, A):
        string_A = ''
        for i in A:
                string_A = string_A + binary_repr(i, 32)[::-1]
        return string_A

    def controlledSP(self, M, K, N, nnz_per_row):
        """生成 M×K 稀疏矩阵，每行恰好 nnz_per_row 个非零元素 (1~99)"""
        I = np.zeros((M, K), dtype=np.int32)
        for r in range(M):
            cols = np.random.choice(K, size=nnz_per_row, replace=False)
            I[r, cols] = np.random.randint(1, 100, size=nnz_per_row)
        print(f"\nSparse matrix (first 8 rows, first 8 cols):\n{I[:8,:8]}")
        Sparse = csr_matrix(I)
        val = Sparse.data.astype(np.int32)
        print(f"\nVal is =\n {val[:16]}... (total {len(val)})")
        col = Sparse.indices.astype(np.int32)
        print(f"\nCol_Idx is =\n {col[:16]}... (total {len(col)})")
        row = Sparse.indptr.astype(np.int32)
        print(f"\nRow_ptr is =\n {row}")
        W = np.random.randint(1, 100, size=(K, N)).astype(np.int32)
        print(f"\nDense matrix (first 8 rows, first 4 cols):\n{W[:8,:4]}")
        O = np.matmul(I, W)
        print(f"\nOutput matrix (first 8 rows, first 4 cols):\n{O[:8,:4]}")
        assert col.size <= 4096//4,  f"col size {col.size} exceeds 1024 (4KB limit)"
        assert val.size <= 4096//4,  f"val size {val.size} exceeds 1024 (4KB limit)"
        return ((val, col, row), I, W, O)


np.random.seed(0)
dataGen = data()
# 64×64 sparse × 64×8 dense, 每行 16 个非零 → col/val 各 1024 个 = 4096B, den/out 各 512 个 = 2048B
((val,col,row), I, den, O) = dataGen.controlledSP(M_SPARSE, K_SPARSE, N_DENSE, NNZ_PER_ROW)
(_,x) = den.shape
(y,_) = I.shape
rowBin = dataGen.arrayToBinary(row)
colBin = dataGen.arrayToBinary(col)
valBin = dataGen.arrayToBinary(val)
denBin = dataGen.matrixToBinary(den)
# 地址布局：每段占用 ≤4KB，从 4KB 对齐地址出发
rowAddr = 0x1000   # row_ptr (260B, 远小于 4KB)
colAddr = 0x2000   # col_idx (4096B, 刚好一页 4KB)
valAddr = 0x3000   # val     (4096B, 刚好一页 4KB)
denAddr = 0x4000   # den     (2048B)
outAddr = 0x5000   # out     (2048B)
instGen = inst()
instr = ''
instr = instr + instGen.load(xsize = row.size, id = 'row', dram_offset = rowAddr, sram_offset = rowAddr)
instr = instr + instGen.load(xsize = col.size, id = 'col', dram_offset = colAddr, sram_offset = colAddr)
instr = instr + instGen.load(xsize = val.size, id = 'val', dram_offset = valAddr, sram_offset = valAddr)
instr = instr + instGen.load(xsize = den.size, id = 'den', dram_offset = denAddr, sram_offset = denAddr)
instr = instr + instGen.spMM(sram_offset_col = colAddr, sram_offset_ptr = rowAddr, sram_offset_den = denAddr, sram_offset_val = valAddr, den_size = den.size, col_size = col.size, row_size = row.size, pr_valid = 1)
instr = instr + instGen.store(xsize = O.size, dram_offset = outAddr, sram_offset = 0)
instCount = len(instr)/256
while(instCount%2 != 0):
    instr = instr + '0'*256
    instCount = len(instr)/256
dram = instrval colReadBlockNum = RegInit(cp.nColInDense.U(32.W))
val colFin = (colReadBlockNum >= ((groupSel + 1.U) << Log2(nNonZeroPerGroup)))

while((len(dram)/8) < rowAddr):
    dram = dram + '0'*32
dram = dram + rowBin
while((len(dram)/8) < colAddr):
    dram = dram + '0'*32
dram = dram + colBin
while((len(dram)/8) < valAddr):
    dram = dram + '0'*32
dram = dram + valBin
while((len(dram)/8) < denAddr):
    dram = dram + '0'*32
dram = dram + denBin
f = open('ram.txt','w')
f.write(dram)