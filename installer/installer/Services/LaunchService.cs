using System.Diagnostics;
using System.Net.Sockets;
using System.Text.Json;

namespace Thuai10.Launcher.Services;

public sealed class LaunchConfig
{
    public int Port { get; set; } = 8888;
    public int ReadyTimeoutSeconds { get; set; } = 30;
    public LaunchProgram? Server { get; set; }
    public LaunchProgram? Interface { get; set; }
    public List<LaunchProgram> Players { get; set; } = new();
}

public sealed class LaunchProgram
{
    public string Path { get; set; } = string.Empty;
    public List<string> Arguments { get; set; } = new();
}

public sealed class LaunchService : IDisposable
{
    private readonly List<Process> processes = new();
    private readonly object gate = new();

    public event Action<string>? Log;

    public bool IsRunning
    {
        get
        {
            lock (gate)
            {
                return processes.Any(p => !p.HasExited);
            }
        }
    }

    public async Task StartAsync(string packageRoot, CancellationToken token)
    {
        if (IsRunning)
        {
            throw new InvalidOperationException("对局已经在运行。");
        }

        string configPath = Path.Combine(packageRoot, "thuai10-launch.json");
        if (!File.Exists(configPath))
        {
            throw new FileNotFoundException("选手包缺少 thuai10-launch.json；请等待其他组确定程序路径与参数。", configPath);
        }

        await using FileStream configStream = File.OpenRead(configPath);
        LaunchConfig config = await JsonSerializer.DeserializeAsync<LaunchConfig>(
            configStream, new JsonSerializerOptions { PropertyNameCaseInsensitive = true }, token)
            ?? throw new InvalidDataException("启动配置为空。");
        if (config.Server is null || config.Port is < 1 or > 65535
            || config.ReadyTimeoutSeconds is < 1 or > 300)
        {
            throw new InvalidDataException("启动配置缺少服务器或端口参数无效。");
        }

        if (await IsPortOpenAsync(config.Port, token))
        {
            throw new InvalidOperationException($"本机端口 {config.Port} 已被占用，请更换端口或关闭占用程序。");
        }

        try
        {
            StartOne(packageRoot, config.Server, "服务器", config.Port);
            await WaitForServerAsync(config.Port, config.ReadyTimeoutSeconds, token);
            if (config.Interface is not null)
            {
                StartOne(packageRoot, config.Interface, "界面", config.Port);
            }

            for (int i = 0; i < config.Players.Count; i++)
            {
                token.ThrowIfCancellationRequested();
                StartOne(packageRoot, config.Players[i], $"选手 {i + 1}", config.Port);
            }

            Log?.Invoke("对局程序已启动。");
        }
        catch
        {
            Stop();
            throw;
        }
    }

    private void StartOne(string root, LaunchProgram program, string name, int port)
    {
        string fullRoot = Path.GetFullPath(root);
        string path = Path.GetFullPath(Path.Combine(fullRoot, program.Path));
        string prefix = Path.TrimEndingDirectorySeparator(fullRoot) + Path.DirectorySeparatorChar;
        if (Path.IsPathRooted(program.Path) || !path.StartsWith(prefix,
                OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{name} 的路径必须位于选手包内。");
        }

        if (!File.Exists(path))
        {
            throw new FileNotFoundException($"未找到{name}程序：{program.Path}", path);
        }

        if (!OperatingSystem.IsWindows())
        {
            UnixFileMode mode = File.GetUnixFileMode(path);
            if ((mode & UnixFileMode.UserExecute) == 0)
            {
                File.SetUnixFileMode(path, mode | UnixFileMode.UserExecute);
            }
        }

        ProcessStartInfo startInfo = new(path)
        {
            WorkingDirectory = Path.GetDirectoryName(path)!,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        foreach (string argument in program.Arguments)
        {
            startInfo.ArgumentList.Add(argument.Replace("{port}", port.ToString(), StringComparison.Ordinal));
        }

        Process process = new() { StartInfo = startInfo, EnableRaisingEvents = true };
        process.OutputDataReceived += (_, e) => { if (e.Data is not null) Log?.Invoke($"{name}: {e.Data}"); };
        process.ErrorDataReceived += (_, e) => { if (e.Data is not null) Log?.Invoke($"{name}: {e.Data}"); };
        process.Exited += (_, _) =>
        {
            try { Log?.Invoke($"{name}已退出，退出码 {process.ExitCode}。"); }
            catch (InvalidOperationException) { }
        };
        if (!process.Start())
        {
            process.Dispose();
            throw new InvalidOperationException($"{name}启动失败。");
        }

        lock (gate)
        {
            processes.Add(process);
        }

        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        Log?.Invoke($"{name}已启动。");
    }

    private static async Task WaitForServerAsync(int port, int timeoutSeconds, CancellationToken token)
    {
        using CancellationTokenSource timeout = CancellationTokenSource.CreateLinkedTokenSource(token);
        timeout.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));
        while (true)
        {
            if (timeout.IsCancellationRequested)
            {
                token.ThrowIfCancellationRequested();
                throw new TimeoutException($"服务器在 {timeoutSeconds} 秒内没有开放端口 {port}。");
            }
            try
            {
                using TcpClient probe = new();
                await probe.ConnectAsync("127.0.0.1", port, timeout.Token);
                return;
            }
            catch (OperationCanceledException) when (!token.IsCancellationRequested)
            {
                throw new TimeoutException($"服务器在 {timeoutSeconds} 秒内没有开放端口 {port}。");
            }
            catch (SocketException)
            {
                await Task.Delay(300, token);
            }
        }
    }

    private static async Task<bool> IsPortOpenAsync(int port, CancellationToken token)
    {
        using TcpClient probe = new();
        try
        {
            await probe.ConnectAsync("127.0.0.1", port, token);
            return true;
        }
        catch (SocketException)
        {
            return false;
        }
    }

    public void Stop()
    {
        lock (gate)
        {
            foreach (Process process in processes)
            {
                try
                {
                    if (!process.HasExited)
                    {
                        process.Kill(entireProcessTree: true);
                    }
                }
                catch (InvalidOperationException) { }
                process.Dispose();
            }

            processes.Clear();
        }

        Log?.Invoke("已停止本次启动的程序。");
    }

    public void Dispose() => Stop();
}
