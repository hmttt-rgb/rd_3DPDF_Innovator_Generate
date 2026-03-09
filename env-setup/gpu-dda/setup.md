# GPU DDA（個別デバイス割り当て）セットアップ

DDA（Discrete Device Assignment）により、物理GPUを Hyper-V 仮想マシンに直接割り当てる手順です。

## 参考文献

- [Microsoft 公式ドキュメント: DDA を使用したグラフィックス デバイスの展開](https://learn.microsoft.com/ja-jp/windows-server/virtualization/hyper-v/deploy/deploying-graphics-devices-using-dda)

---

## GPUの新規割り当て手順

対象GPU: **NVIDIA RTX 2000 Ada Generation**  
以下はすべて**ホストOS（物理サーバー）**上で PowerShell（管理者モード）を使用して実行します。

### 1. DDA 対応確認

以下のスクリプトをダウンロードしてそのまま実行します:

- [SurveyDDA.ps1](https://github.com/MicrosoftDocs/Virtualization-Documentation/blob/live/hyperv-tools/DiscreteDeviceAssignment/SurveyDDA.ps1)

確認ポイント:

- `assignment can work` と表示されれば割り当て可能
- `PCIROOT(0)#PCI(0100)#PCI(0000)` — GPUのロケーションパス（後続手順で使用）
- `at least: 337 MB of MMIO gap space` — 必要なMMIO領域サイズ

> **MMIO (Memory-Mapped I/O)** とは、CPUがGPUなどのデバイスと直接通信するために使用する特別なメモリ空間です。

### 2. MMIO 領域の決定

スクリプトで示された必要量（337 MB）を十分にカバーできる、2のべき乗の値を選択します。  
→ 今回は **512MB** を採用

### 3. VM の Automatic Stop Action を設定

```powershell
Set-VM -Name HyperV2 -AutomaticStopAction TurnOff
```

### 4. VM の MMIO 領域を設定

```powershell
Set-VM -GuestControlledCacheTypes $true -VMName "HyperV2"
Set-VM -VMName "HyperV2" -HighMemoryMappedIoSpace 512MB
```

### 5. ホストから GPU をマウント解除

ホストOSとVMが1つのGPUを取り合わないようにするために必要な操作です。

**デバイスの無効化:**

デバイスマネージャー > ディスプレイアダプター > NVIDIA を右クリック > **無効化**

**デバイスの切り離し:**

```powershell
$locationPath = "PCIROOT(0)#PCI(0100)#PCI(0000)"
Dismount-VmHostAssignableDevice -LocationPath $locationPath -Force
```

### 6. GPU を VM に割り当て

```powershell
$locationPath = "PCIROOT(0)#PCI(0100)#PCI(0000)"
Add-VMAssignableDevice -LocationPath $locationPath -VMName "HyperV2"
```

### 7. 割り当ての確認

```powershell
Get-VMAssignableDevice -VMName "HyperV2"
```

### 8. VM 内で NVIDIA ドライバーをインストール

VM（HyperV2）にログインしてドライバーをインストールします。

- **ドライバー**: NVIDIA RTX Server Driver Release 580 R580 U4 (581.42) | Windows Server 2025
- **URL**: https://www.nvidia.com/ja-jp/drivers/details/254702/

> **注意**: ドライバーインストール前はデバイスマネージャーに「Windows基本のディスプレイ～」が黄色い三角マーク付きで表示されますが、ドライバーインストール後に解消されます。解消しない場合はアンインストール→再起動で解決します。

---

## GPU の別 VM への付け替え手順

仮想マシン間（例: HyperV2 → HyperV1）でGPUを付け替える手順です。  
以下はすべて**ホストサーバー（物理マシン）**で実行します。

> **前提**: 移行先・移行元の両方の仮想マシンを**シャットダウン**してから作業を開始してください。

### 1. 移行元のGPUロケーションパスを取得

```powershell
$gpuPath = (Get-VMAssignableDevice -VMName HyperV2).LocationPath
```

> 参考: `$gpuPath` の結果例 → `PCIROOT(0)#PCI(0100)#PCI(0000)`

### 2. 移行元（HyperV2）からGPUを取り外し

```powershell
Remove-VMAssignableDevice -VMName HyperV2 -LocationPath $gpuPath
```

### 3. 移行先（HyperV1）の設定

```powershell
Set-VM -VMName HyperV1 -AutomaticStopAction TurnOff
Set-VM -VMName HyperV1 -GuestControlledCacheTypes $true -LowMemoryMappedIoSpace 3Gb -HighMemoryMappedIoSpace 33Gb
```

### 4. 移行先（HyperV1）へGPUを割り当て

```powershell
Add-VMAssignableDevice -VMName HyperV1 -LocationPath $gpuPath
```
