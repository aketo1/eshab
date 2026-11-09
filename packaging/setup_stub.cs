// The Eshab Setup, in Eshab's own identity: a glass window over your blurred
// wallpaper, the «الملف ينسحب» mark as the progress (the page fills with
// liquid while the files are copied, its surface waving until it is full), and the material chosen by dipping the drop into one
// of three jars. One file: Eshab is a zip appended to this program
// (packaging/make_setup.py); the mark's masks are embedded resources.
// Installs for this user only, into %LOCALAPPDATA%\Programs\Eshab, no admin.
// Built with the C# compiler and WPF that ship with Windows (.NET 4).
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Effects;
using System.Windows.Media.Imaging;
using System.Windows.Shapes;

[assembly: AssemblyTitle("Eshab Setup")]
[assembly: AssemblyProduct("Eshab")]
[assembly: AssemblyVersion("2.0.0.0")]

static class Program
{
    [STAThread]
    static void Main()
    {
        var app = new Application();
        app.ShutdownMode = ShutdownMode.OnMainWindowClose;
        app.Run(new SetupWindow());
    }
}

class Material
{
    public string Key, Name;
    public Color Light, Deep, Accent, OnAccent;
    public double Alpha;
    public Material(string key, string name, string light, string deep, string accent, string onAccent, double alpha)
    {
        Key = key; Name = name; Alpha = alpha;
        Light = Hex(light); Deep = Hex(deep); Accent = Hex(accent); OnAccent = Hex(onAccent);
    }
    public static Color Hex(string hex)
    {
        return (Color)ColorConverter.ConvertFromString(hex);
    }
}

class SetupWindow : Window
{
    // The same three materials as eshab/qml/Eshab/Theme.qml.
    static readonly Material[] Materials = {
        new Material("honey", "ذهبي", "#FFD985", "#DB7817", "#F2A33A", "#3D2204", 0.97),
        new Material("clear", "شفاف", "#FFFFFF", "#D5DCE8", "#F2F4F8", "#1C1C1E", 0.42),
        new Material("ink", "أزرق", "#B3BCFF", "#3138C8", "#5560F0", "#FFFFFF", 0.97),
    };
    const double LogoSize = 132;

    string target;
    TextBlock place;
    Material material = Materials[0];
    readonly GradientStop liquidTop = new GradientStop(), liquidBottom = new GradientStop(Colors.Transparent, 1);
    readonly SolidColorBrush accentBrush = new SolidColorBrush(), onAccentBrush = new SolidColorBrush();
    readonly TranslateTransform liquidLevel = new TranslateTransform(), waveShift = new TranslateTransform();
    readonly TranslateTransform dropMove = new TranslateTransform();
    readonly ScaleTransform dropStretch = new ScaleTransform(1, 1), logoScale = new ScaleTransform(1, 1);
    readonly TranslateTransform logoMove = new TranslateTransform();
    readonly Canvas backdrop = new Canvas();
    readonly Image wallpaper = new Image();
    StackPanel choices;
    TextBlock title, subtitle, percent, status;
    Border action;
    TextBlock actionText;
    Toggle startup, menu, desktop;
    readonly Border[] jars = new Border[3];
    string state = "ready";          // ready | working | done | failed

    public SetupWindow()
    {
        target = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Eshab");
        Title = "تثبيت «اسحب»";
        Width = 500;
        Height = 756;
        WindowStyle = WindowStyle.None;
        AllowsTransparency = true;
        Background = Brushes.Transparent;
        ResizeMode = ResizeMode.NoResize;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        FlowDirection = FlowDirection.RightToLeft;
        FontFamily = new FontFamily("Segoe UI");
        UseLayoutRounding = true;
        try { Icon = BitmapFrame.Create(Resource("icon.png")); } catch { }

        var root = new Grid { Margin = new Thickness(26) };
        var shadow = new Border { CornerRadius = new CornerRadius(30), Background = new SolidColorBrush(Color.FromArgb(255, 20, 20, 24)) };
        shadow.Effect = new DropShadowEffect { BlurRadius = 46, ShadowDepth = 10, Direction = 270, Opacity = 0.5, Color = Colors.Black };
        root.Children.Add(shadow);

        var glass = new Border { CornerRadius = new CornerRadius(30), ClipToBounds = true };
        var surface = new Grid();
        // Your wallpaper, blurred, lined up with where the window stands: the
        // same glass as the wheel and the island.
        wallpaper.Stretch = Stretch.UniformToFill;
        wallpaper.Effect = new BlurEffect { Radius = 70, KernelType = KernelType.Gaussian, RenderingBias = RenderingBias.Performance };
        backdrop.Children.Add(wallpaper);
        backdrop.IsHitTestVisible = false;
        surface.Children.Add(backdrop);
        surface.Children.Add(new Border { Background = new SolidColorBrush(Color.FromArgb(150, 24, 24, 29)) });
        surface.Children.Add(new Border
        {
            Background = new LinearGradientBrush(Color.FromArgb(36, 255, 255, 255), Color.FromArgb(0, 255, 255, 255), 90)
        });
        surface.Children.Add(Content_());
        glass.Child = surface;
        root.Children.Add(glass);
        root.Children.Add(new Border
        {
            CornerRadius = new CornerRadius(30), BorderThickness = new Thickness(1), IsHitTestVisible = false,
            BorderBrush = new LinearGradientBrush(Color.FromArgb(110, 255, 255, 255), Color.FromArgb(18, 255, 255, 255), 90)
        });
        Content = root;

        LoadWallpaper();
        LocationChanged += delegate { PlaceWallpaper(); };
        Loaded += delegate { PlaceWallpaper(); Intro(); };
        MouseLeftButtonDown += delegate (object s, MouseButtonEventArgs e) { if (e.ButtonState == MouseButtonState.Pressed) { try { DragMove(); } catch { } } };
        KeyDown += delegate (object s, KeyEventArgs e)
        {
            if (e.Key == Key.Escape && state != "working") Close();
            if (e.Key == Key.Enter) Act();
        };
        Paint(material, false);
    }

    // -- layout -----------------------------------------------------------------

    UIElement Content_()
    {
        var page = new Grid();
        page.Children.Add(CloseButton());

        var column = new StackPanel { Margin = new Thickness(34, 30, 34, 0) };
        var logoHost = new Grid { Width = LogoSize, Height = LogoSize, HorizontalAlignment = HorizontalAlignment.Center };
        logoHost.RenderTransformOrigin = new Point(0.5, 0.5);
        var logoGroup = new TransformGroup();
        logoGroup.Children.Add(logoScale);
        logoGroup.Children.Add(logoMove);
        logoHost.RenderTransform = logoGroup;
        logoHost.Children.Add(Mark());
        column.Children.Add(logoHost);

        title = Text("اسحب", 30, FontWeights.SemiBold, Colors.White);
        title.Margin = new Thickness(0, 10, 0, 0);
        title.HorizontalAlignment = HorizontalAlignment.Center;
        column.Children.Add(title);
        subtitle = Text("حوّل ملفاتك وعدّلها بسحبة واحدة", 14, FontWeights.Normal, Color.FromArgb(190, 255, 255, 255));
        subtitle.HorizontalAlignment = HorizontalAlignment.Center;
        subtitle.TextAlignment = TextAlignment.Center;
        subtitle.Margin = new Thickness(0, 4, 0, 0);
        column.Children.Add(subtitle);

        percent = Text("", 22, FontWeights.SemiBold, Colors.White);
        percent.HorizontalAlignment = HorizontalAlignment.Center;
        percent.FlowDirection = FlowDirection.LeftToRight;
        percent.Opacity = 0;

        choices = new StackPanel { Margin = new Thickness(0, 18, 0, 0) };
        var label = Text("اختر اللون", 13, FontWeights.SemiBold, Color.FromArgb(200, 255, 255, 255));
        label.Margin = new Thickness(4, 0, 4, 10);
        choices.Children.Add(label);
        var jarRow = new UniformGrid_(3);
        for (int i = 0; i < Materials.Length; i++) jarRow.Add(Jar(i));
        choices.Children.Add(jarRow.Panel);

        var options = new Border
        {
            Margin = new Thickness(0, 14, 0, 0), CornerRadius = new CornerRadius(18), Padding = new Thickness(16, 4, 16, 4),
            Background = new SolidColorBrush(Color.FromArgb(26, 255, 255, 255)),
            BorderBrush = new SolidColorBrush(Color.FromArgb(30, 255, 255, 255)), BorderThickness = new Thickness(1)
        };
        var list = new StackPanel();
        startup = new Toggle(this, "التشغيل تلقائيًا مع ويندوز");
        menu = new Toggle(this, "الإضافة لقائمة الزر الأيمن في المستكشف");
        desktop = new Toggle(this, "اختصار على سطح المكتب");
        list.Children.Add(startup.Row);
        list.Children.Add(Divider());
        list.Children.Add(menu.Row);
        list.Children.Add(Divider());
        list.Children.Add(desktop.Row);
        list.Children.Add(Divider());
        list.Children.Add(PlaceRow());
        options.Child = list;
        choices.Children.Add(options);
        column.Children.Add(choices);

        status = Text("", 12.5, FontWeights.Normal, Color.FromArgb(170, 255, 255, 255));
        status.HorizontalAlignment = HorizontalAlignment.Center;
        status.TextAlignment = TextAlignment.Center;
        status.TextWrapping = TextWrapping.Wrap;
        status.Margin = new Thickness(0, 8, 0, 0);

        var bottom = new StackPanel { VerticalAlignment = VerticalAlignment.Bottom, Margin = new Thickness(34, 0, 34, 22) };
        bottom.Children.Add(percent);
        bottom.Children.Add(status);
        action = new Border
        {
            Height = 50, Width = 210, CornerRadius = new CornerRadius(25), Background = accentBrush, Cursor = Cursors.Hand,
            HorizontalAlignment = HorizontalAlignment.Center, Margin = new Thickness(0, 12, 0, 0),
            RenderTransformOrigin = new Point(0.5, 0.5), RenderTransform = new ScaleTransform(1, 1)
        };
        action.Effect = new DropShadowEffect { BlurRadius = 22, ShadowDepth = 4, Direction = 270, Opacity = 0.35, Color = Colors.Black };
        actionText = Text("تثبيت", 16, FontWeights.SemiBold, Colors.Black);
        actionText.Foreground = onAccentBrush;
        actionText.HorizontalAlignment = HorizontalAlignment.Center;
        actionText.VerticalAlignment = VerticalAlignment.Center;
        action.Child = actionText;
        action.MouseEnter += delegate { Spring(action, 1.04); };
        action.MouseLeave += delegate { Spring(action, 1.0); };
        action.MouseLeftButtonDown += delegate (object s, MouseButtonEventArgs e) { e.Handled = true; Spring(action, 0.96); };
        action.MouseLeftButtonUp += delegate (object s, MouseButtonEventArgs e) { e.Handled = true; Spring(action, 1.04); Act(); };
        bottom.Children.Add(action);
        var note = Text("يعمل محليًا على جهازك · بدون صلاحيات مسؤول", 11.5, FontWeights.Normal, Color.FromArgb(120, 255, 255, 255));
        note.HorizontalAlignment = HorizontalAlignment.Center;
        note.Margin = new Thickness(0, 10, 0, 0);
        bottom.Children.Add(note);

        page.Children.Add(column);
        page.Children.Add(bottom);
        return page;
    }

    UIElement CloseButton()
    {
        var close = new Border
        {
            Width = 30, Height = 30, CornerRadius = new CornerRadius(15), Cursor = Cursors.Hand,
            HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Top,
            Margin = new Thickness(0, 16, 16, 0), Background = new SolidColorBrush(Color.FromArgb(28, 255, 255, 255))
        };
        var cross = Text("✕", 12, FontWeights.Normal, Color.FromArgb(200, 255, 255, 255));
        cross.HorizontalAlignment = HorizontalAlignment.Center;
        cross.VerticalAlignment = VerticalAlignment.Center;
        close.Child = cross;
        close.MouseEnter += delegate { close.Background = new SolidColorBrush(Color.FromArgb(60, 255, 255, 255)); };
        close.MouseLeave += delegate { close.Background = new SolidColorBrush(Color.FromArgb(28, 255, 255, 255)); };
        close.MouseLeftButtonUp += delegate (object s, MouseButtonEventArgs e) { e.Handled = true; if (state != "working") Close(); };
        close.MouseLeftButtonDown += delegate (object s, MouseButtonEventArgs e) { e.Handled = true; };
        return close;
    }

    // Where Eshab goes: %LOCALAPPDATA%\Programs\Eshab unless you pick a folder.
    UIElement PlaceRow()
    {
        var row = new Grid { Height = 44, Background = Brushes.Transparent };
        var label = Text("مكان التثبيت", 13.5, FontWeights.Normal, Color.FromArgb(230, 255, 255, 255));
        label.VerticalAlignment = VerticalAlignment.Center;
        row.Children.Add(label);
        var right = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center };
        place = Text(Shorten(target), 12, FontWeights.Normal, Color.FromArgb(160, 255, 255, 255));
        place.FlowDirection = FlowDirection.LeftToRight;
        place.ToolTip = target;
        place.MaxWidth = 190;
        place.TextTrimming = TextTrimming.CharacterEllipsis;
        place.VerticalAlignment = VerticalAlignment.Center;
        var change = new TextBlock { Text = "تغيير", FontSize = 13, FontWeight = FontWeights.SemiBold, Foreground = accentBrush, Cursor = Cursors.Hand, Margin = new Thickness(10, 0, 0, 0), VerticalAlignment = VerticalAlignment.Center };
        change.MouseLeftButtonDown += delegate (object s, MouseButtonEventArgs e) { e.Handled = true; };
        change.MouseLeftButtonUp += delegate (object s, MouseButtonEventArgs e) { e.Handled = true; if (state == "ready" || state == "failed") Pick(); };
        right.Children.Add(change);
        right.Children.Add(place);
        row.Children.Add(right);
        return row;
    }

    static string Shorten(string path)
    {
        string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        return path.StartsWith(home, StringComparison.OrdinalIgnoreCase) ? "~" + path.Substring(home.Length) : path;
    }

    void Pick()
    {
        using (var dialog = new System.Windows.Forms.FolderBrowserDialog())
        {
            dialog.Description = "اختر المجلد اللي ينزل فيه «اسحب»";
            dialog.ShowNewFolderButton = true;
            dialog.SelectedPath = System.IO.Path.GetDirectoryName(target);
            if (dialog.ShowDialog() != System.Windows.Forms.DialogResult.OK || string.IsNullOrEmpty(dialog.SelectedPath)) return;
            string chosen = dialog.SelectedPath;
            if (!string.Equals(System.IO.Path.GetFileName(chosen.TrimEnd(System.IO.Path.DirectorySeparatorChar)), "Eshab", StringComparison.OrdinalIgnoreCase))
                chosen = System.IO.Path.Combine(chosen, "Eshab");
            target = chosen;
            place.Text = Shorten(target);
            place.ToolTip = target;
        }
    }

    static UIElement Divider()
    {
        return new Border { Height = 1, Background = new SolidColorBrush(Color.FromArgb(22, 255, 255, 255)), Margin = new Thickness(0, 2, 0, 2) };
    }

    // The mark: a glass page (the vessel), the liquid inside it, two text
    // lines, and the drop in the bitten corner.
    UIElement Mark()
    {
        double unit = LogoSize / 100.0;
        var mark = new Grid { Width = LogoSize, Height = LogoSize, FlowDirection = FlowDirection.LeftToRight };
        var vessel = new ImageBrush(Resource("vessel.png")) { Stretch = Stretch.Fill };

        mark.Children.Add(new Rectangle { Fill = new SolidColorBrush(Color.FromArgb(40, 255, 255, 255)), OpacityMask = vessel });

        var liquid = new Canvas { OpacityMask = vessel, ClipToBounds = true };
        var liquidBrush = new LinearGradientBrush { StartPoint = new Point(0, 0), EndPoint = new Point(0, 1) };
        liquidBrush.GradientStops.Add(liquidTop);
        liquidBrush.GradientStops.Add(liquidBottom);
        var wave = new System.Windows.Shapes.Path { Fill = liquidBrush, Data = WaveGeometry(LogoSize) };
        var waveGroup = new TransformGroup();
        waveGroup.Children.Add(waveShift);
        waveGroup.Children.Add(liquidLevel);
        wave.RenderTransform = waveGroup;
        liquid.Children.Add(wave);
        mark.Children.Add(liquid);
        SetLevel(0, false);

        mark.Children.Add(new Rectangle { Fill = new SolidColorBrush(Color.FromArgb(150, 255, 255, 255)), OpacityMask = new ImageBrush(Resource("rim.png")) { Stretch = Stretch.Fill } });

        var lines = new Canvas();
        lines.Children.Add(Line(47, 50, 24, unit));
        lines.Children.Add(Line(56, 60, 15, unit));
        mark.Children.Add(lines);

        var drop = new Ellipse { Width = 24 * unit, Height = 24 * unit, HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top };
        drop.Margin = new Thickness((27.5 - 12) * unit, (22.5 - 12) * unit, 0, 0);
        var dropBrush = new RadialGradientBrush { GradientOrigin = new Point(0.35, 0.3), Center = new Point(0.45, 0.4), RadiusX = 0.7, RadiusY = 0.7 };
        dropBrush.GradientStops.Add(liquidTop);
        dropBrush.GradientStops.Add(liquidBottom);
        drop.Fill = dropBrush;
        drop.Stroke = new SolidColorBrush(Color.FromArgb(120, 255, 255, 255));
        drop.StrokeThickness = 1;
        drop.RenderTransformOrigin = new Point(0.5, 0.5);
        var dropGroup = new TransformGroup();
        dropGroup.Children.Add(dropStretch);
        dropGroup.Children.Add(dropMove);
        drop.RenderTransform = dropGroup;
        mark.Children.Add(drop);

        // The liquid's surface moves for as long as the window is open.
        var flow = new DoubleAnimation(0, -LogoSize, new Duration(TimeSpan.FromSeconds(2.4))) { RepeatBehavior = RepeatBehavior.Forever };
        waveShift.BeginAnimation(TranslateTransform.XProperty, flow);
        return mark;
    }

    static Rectangle Line(double x, double y, double length, double unit)
    {
        var line = new Rectangle
        {
            Width = length * unit, Height = 4.4 * unit, RadiusX = 2.2 * unit, RadiusY = 2.2 * unit,
            Fill = new SolidColorBrush(Color.FromArgb(120, 255, 255, 255))
        };
        Canvas.SetLeft(line, x * unit);
        Canvas.SetTop(line, (y - 2.2) * unit);
        return line;
    }

    static Geometry WaveGeometry(double size)
    {
        // Two wavelengths wide so sliding by one keeps it seamless.
        var figure = new PathFigure { StartPoint = new Point(0, size), IsClosed = true };
        double amplitude = size * 0.022, length = size;
        figure.Segments.Add(new LineSegment(new Point(0, 0), true));
        for (double x = 0; x <= size * 3; x += 4)
            figure.Segments.Add(new LineSegment(new Point(x, amplitude * Math.Sin(x / length * Math.PI * 2)), true));
        figure.Segments.Add(new LineSegment(new Point(size * 3, size), true));
        var geometry = new PathGeometry();
        geometry.Figures.Add(figure);
        return geometry;
    }

    void SetLevel(double level, bool animate)
    {
        // The page spans y 24..88 of the 100 box; empty sits just below it.
        double unit = LogoSize / 100.0;
        double y = (88 - 64 * Math.Max(0, Math.Min(1, level))) * unit + (level <= 0 ? 6 * unit : 0);
        if (!animate) { liquidLevel.Y = y; return; }
        liquidLevel.BeginAnimation(TranslateTransform.YProperty,
            new DoubleAnimation(y, new Duration(TimeSpan.FromMilliseconds(420))) { EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut } });
    }

    FrameworkElement Jar(int index)
    {
        var m = Materials[index];
        var cell = new StackPanel { Cursor = Cursors.Hand, HorizontalAlignment = HorizontalAlignment.Center };
        var jar = new Border
        {
            Width = 58, Height = 58, CornerRadius = new CornerRadius(29), BorderThickness = new Thickness(2),
            BorderBrush = Brushes.Transparent, Padding = new Thickness(4), RenderTransformOrigin = new Point(0.5, 0.5),
            RenderTransform = new ScaleTransform(1, 1), Background = new SolidColorBrush(Color.FromArgb(24, 255, 255, 255))
        };
        var fill = new LinearGradientBrush(m.Light, m.Deep, 90);
        fill.Opacity = m.Alpha;
        var inside = new Border { CornerRadius = new CornerRadius(25), Background = fill, BorderThickness = new Thickness(1), BorderBrush = new SolidColorBrush(Color.FromArgb(90, 255, 255, 255)) };
        jar.Child = inside;
        jars[index] = jar;
        cell.Children.Add(jar);
        var name = Text(m.Name, 12.5, FontWeights.Normal, Color.FromArgb(210, 255, 255, 255));
        name.HorizontalAlignment = HorizontalAlignment.Center;
        name.Margin = new Thickness(0, 6, 0, 0);
        cell.Children.Add(name);
        cell.MouseEnter += delegate { if (material != m) Spring(jar, 1.06); };
        cell.MouseLeave += delegate { if (material != m) Spring(jar, 1.0); };
        cell.MouseLeftButtonDown += delegate (object s, MouseButtonEventArgs e) { e.Handled = true; };
        cell.MouseLeftButtonUp += delegate (object s, MouseButtonEventArgs e) { e.Handled = true; if (state == "ready") Paint(m, true); };
        return cell;
    }

    // -- colour: the whole window follows the chosen material -------------------

    void Paint(Material m, bool animate)
    {
        material = m;
        Color top = m.Light, bottom = m.Deep;
        top.A = bottom.A = (byte)(255 * m.Alpha);
        Fade(liquidTop, top, animate);
        Fade(liquidBottom, bottom, animate);
        Fade(accentBrush, m.Accent, animate);
        Fade(onAccentBrush, m.OnAccent, animate);
        for (int i = 0; i < jars.Length; i++)
        {
            if (jars[i] == null) continue;
            bool chosen = Materials[i] == m;
            jars[i].BorderBrush = new SolidColorBrush(chosen ? Color.FromArgb(230, 255, 255, 255) : Colors.Transparent);
            Spring(jars[i], chosen ? 1.1 : 1.0);
        }
        if (animate)
        {
            // The drop dips: a little squash, then back.
            var dip = new DoubleAnimationUsingKeyFrames();
            dip.KeyFrames.Add(new EasingDoubleKeyFrame(0.82, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(110))));
            dip.KeyFrames.Add(new EasingDoubleKeyFrame(1.0, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(520)), new ElasticEase { Oscillations = 2, Springiness = 5 }));
            dropStretch.BeginAnimation(ScaleTransform.ScaleYProperty, dip);
        }
    }

    static void Fade(GradientStop stop, Color color, bool animate)
    {
        if (!animate) { stop.Color = color; return; }
        stop.BeginAnimation(GradientStop.ColorProperty, new ColorAnimation(color, new Duration(TimeSpan.FromMilliseconds(380))));
    }

    static void Fade(SolidColorBrush brush, Color color, bool animate)
    {
        if (!animate) { brush.Color = color; return; }
        brush.BeginAnimation(SolidColorBrush.ColorProperty, new ColorAnimation(color, new Duration(TimeSpan.FromMilliseconds(380))));
    }

    static void Spring(UIElement element, double to)
    {
        var scale = element.RenderTransform as ScaleTransform;
        if (scale == null) return;
        var ease = new ElasticEase { Oscillations = 1, Springiness = 6 };
        var animation = new DoubleAnimation(to, new Duration(TimeSpan.FromMilliseconds(380))) { EasingFunction = ease };
        scale.BeginAnimation(ScaleTransform.ScaleXProperty, animation);
        scale.BeginAnimation(ScaleTransform.ScaleYProperty, animation);
    }

    static void Show(UIElement element, double opacity, int ms)
    {
        element.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(opacity, new Duration(TimeSpan.FromMilliseconds(ms))));
    }

    static TextBlock Text(string text, double size, FontWeight weight, Color color)
    {
        return new TextBlock { Text = text, FontSize = size, FontWeight = weight, Foreground = new SolidColorBrush(color) };
    }

    // -- the wallpaper behind the glass ---------------------------------------------

    void LoadWallpaper()
    {
        try
        {
            string path = null;
            using (var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Control Panel\Desktop"))
                if (key != null) path = key.GetValue("WallPaper") as string;
            if (string.IsNullOrEmpty(path) || !File.Exists(path))
                path = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), @"Microsoft\Windows\Themes\TranscodedWallpaper");
            if (!File.Exists(path)) return;
            var image = new BitmapImage();
            using (var stream = File.OpenRead(path))
            {
                image.BeginInit();
                image.CacheOption = BitmapCacheOption.OnLoad;
                image.DecodePixelWidth = 960;
                image.StreamSource = stream;
                image.EndInit();
            }
            image.Freeze();
            wallpaper.Source = image;
        }
        catch { }
    }

    void PlaceWallpaper()
    {
        const double over = 140;     // the blur fades at the image's edges: keep them out of sight
        wallpaper.Width = SystemParameters.PrimaryScreenWidth + over * 2;
        wallpaper.Height = SystemParameters.PrimaryScreenHeight + over * 2;
        Canvas.SetLeft(wallpaper, -Left - 26 - over);
        Canvas.SetTop(wallpaper, -Top - 26 - over);
    }

    // -- the flow ---------------------------------------------------------------------

    void Intro()
    {
        Opacity = 0;
        BeginAnimation(OpacityProperty, new DoubleAnimation(1, new Duration(TimeSpan.FromMilliseconds(260))));
        logoScale.ScaleX = logoScale.ScaleY = 0.7;
        var grow = new DoubleAnimation(1, new Duration(TimeSpan.FromMilliseconds(700))) { EasingFunction = new ElasticEase { Oscillations = 1, Springiness = 5 } };
        logoScale.BeginAnimation(ScaleTransform.ScaleXProperty, grow);
        logoScale.BeginAnimation(ScaleTransform.ScaleYProperty, grow);
        // A first taste of liquid in the page.
        SetLevel(0.18, true);
    }

    void Act()
    {
        if (state == "ready" || state == "failed") Begin();
        else if (state == "done") Close();
    }

    void Begin()
    {
        state = "working";
        string flags = "--setup-finish --material " + material.Key + (startup.On ? " --startup" : "") + (menu.On ? " --shellmenu" : "") + (desktop.On ? " --desktop" : "");
        Show(choices, 0, 220);
        choices.IsHitTestVisible = false;
        Show(action, 0, 200);
        action.IsHitTestVisible = false;
        title.Text = "جارٍ التثبيت…";
        subtitle.Text = "لحظات ويكون البرنامج جاهزًا";
        status.Foreground = new SolidColorBrush(Color.FromArgb(170, 255, 255, 255));
        Show(percent, 1, 300);
        // The mark moves down into the space the options left and grows.
        var move = new DoubleAnimation(70, new Duration(TimeSpan.FromMilliseconds(600))) { EasingFunction = new CubicEase { EasingMode = EasingMode.EaseInOut } };
        logoMove.BeginAnimation(TranslateTransform.YProperty, move);
        var grow = new DoubleAnimation(1.3, new Duration(TimeSpan.FromMilliseconds(600))) { EasingFunction = new CubicEase { EasingMode = EasingMode.EaseInOut } };
        logoScale.BeginAnimation(ScaleTransform.ScaleXProperty, grow);
        logoScale.BeginAnimation(ScaleTransform.ScaleYProperty, grow);
        var lower = new DoubleAnimation(94, new Duration(TimeSpan.FromMilliseconds(600))) { EasingFunction = new CubicEase { EasingMode = EasingMode.EaseInOut } };
        title.RenderTransform = new TranslateTransform();
        title.RenderTransform.BeginAnimation(TranslateTransform.YProperty, lower);
        subtitle.RenderTransform = new TranslateTransform();
        subtitle.RenderTransform.BeginAnimation(TranslateTransform.YProperty, lower);
        SetLevel(0.02, true);
        var worker = new Thread(delegate () { Install(flags); }) { IsBackground = true };
        worker.Start();
    }

    void Ui(Action step) { Dispatcher.BeginInvoke(step); }

    void Install(string flags)
    {
        try
        {
            Ui(delegate { status.Text = "إغلاق «اسحب» إن كان يعمل…"; });
            CloseRunning();
            Ui(delegate { status.Text = "جارٍ نسخ الملفات…"; });
            Unpack();
            Ui(delegate { status.Text = "جارٍ تجهيز الاختصارات…"; });
            string exe = System.IO.Path.Combine(target, "Eshab.exe");
            using (var finish = Process.Start(new ProcessStartInfo(exe, flags) { UseShellExecute = false, WorkingDirectory = target }))
                finish.WaitForExit(60000);
            Process.Start(new ProcessStartInfo(exe) { UseShellExecute = true, WorkingDirectory = target });
            Ui(Finished);
        }
        catch (Exception error)
        {
            string message = error.Message;
            Ui(delegate
            {
                state = "failed";
                title.Text = "تعذّر إكمال التثبيت";
                subtitle.Text = "";
                status.Text = message;
                status.Foreground = new SolidColorBrush(Material.Hex("#FF8A8A"));
                actionText.Text = "حاول مرة أخرى";
                Show(action, 1, 200);
                action.IsHitTestVisible = true;
                Show(percent, 0, 200);
                SetLevel(0.18, true);
            });
        }
    }

    void Finished()
    {
        state = "done";
        SetLevel(1, true);
        percent.Text = "100%";
        title.Text = "جاهز";
        subtitle.Text = "اسحب أي ملف مع Shift لتحويله، أو مع Alt لفتح الأدوات.";
        status.Text = "تجد أيقونة «اسحب» الآن بجانب الساعة.";
        // The page is full: the liquid keeps its gentle wave, nothing else moves.
        actionText.Text = "ابدأ";
        Show(action, 1, 300);
        action.IsHitTestVisible = true;
    }

    static void CloseRunning()
    {
        foreach (var running in Process.GetProcessesByName("Eshab"))
        {
            string file = null;
            try { file = running.MainModule.FileName; } catch { }
            if (file == null) continue;
            try
            {
                using (var quit = Process.Start(new ProcessStartInfo(file, "--quit") { UseShellExecute = false, CreateNoWindow = true }))
                    quit.WaitForExit(8000);
            }
            catch { }
            break;      // one request reaches the running Eshab
        }
        DateTime deadline = DateTime.Now.AddSeconds(12);
        while (Process.GetProcessesByName("Eshab").Length > 0 && DateTime.Now < deadline)
            Thread.Sleep(300);
        if (Process.GetProcessesByName("Eshab").Length > 0)
            throw new Exception("برنامج «اسحب» ما زال يعمل. أغلقه من الأيقونة بجانب الساعة ثم حاول مرة أخرى.");
    }

    void Unpack()
    {
        string old = System.IO.Path.Combine(target, "_internal");
        if (Directory.Exists(old))
            Directory.Delete(old, true);        // a fresh copy: nothing left from an older version
        try { Directory.CreateDirectory(target); File.WriteAllText(System.IO.Path.Combine(target, ".eshab-write-test"), ""); File.Delete(System.IO.Path.Combine(target, ".eshab-write-test")); }
        catch (UnauthorizedAccessException) { throw new Exception("هذا المجلد يحتاج صلاحيات مسؤول. اختر مجلد ثاني من «تغيير»."); }
        string root = System.IO.Path.GetFullPath(target).TrimEnd('\\') + "\\";
        string self = Assembly.GetExecutingAssembly().Location;
        using (var file = File.OpenRead(self))
        using (var zip = new ZipArchive(file, ZipArchiveMode.Read))
        {
            long total = 0, done = 0;
            foreach (var entry in zip.Entries) total += entry.Length;
            byte[] buffer = new byte[1 << 20];
            int shown = -1;
            foreach (var entry in zip.Entries)
            {
                string relative = entry.FullName.Replace('/', '\\');
                if (relative.StartsWith("Eshab\\")) relative = relative.Substring(6);
                string destination = System.IO.Path.GetFullPath(System.IO.Path.Combine(target, relative));
                if (!destination.StartsWith(root, StringComparison.OrdinalIgnoreCase)) continue;
                if (entry.Name.Length == 0) { Directory.CreateDirectory(destination); continue; }
                Directory.CreateDirectory(System.IO.Path.GetDirectoryName(destination));
                using (var source = entry.Open())
                using (var output = File.Create(destination))
                {
                    int read;
                    while ((read = source.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        output.Write(buffer, 0, read);
                        done += read;
                        int value = total > 0 ? (int)(done * 100 / total) : 100;
                        if (value != shown)
                        {
                            shown = value;
                            int now = value;
                            Ui(delegate { percent.Text = now + "%"; SetLevel(0.02 + 0.93 * now / 100.0, true); });
                        }
                    }
                }
            }
        }
    }

    static BitmapSource Resource(string name)
    {
        using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("Eshab." + name))
        {
            var image = new BitmapImage();
            image.BeginInit();
            image.CacheOption = BitmapCacheOption.OnLoad;
            image.StreamSource = stream;
            image.EndInit();
            image.Freeze();
            return image;
        }
    }

    // -- small pieces -------------------------------------------------------------------

    class UniformGrid_
    {
        public readonly Grid Panel = new Grid();
        int count;
        public UniformGrid_(int columns)
        {
            for (int i = 0; i < columns; i++) Panel.ColumnDefinitions.Add(new ColumnDefinition());
        }
        public void Add(UIElement element)
        {
            Grid.SetColumn(element, count++);
            Panel.Children.Add(element);
        }
    }

    // A glass switch: the knob slides and the track fills with the material.
    class Toggle
    {
        public readonly Grid Row = new Grid { Height = 40, Cursor = Cursors.Hand, Background = Brushes.Transparent };
        public bool On = true;
        readonly Border track, knob;
        readonly TranslateTransform slide = new TranslateTransform();

        public Toggle(SetupWindow owner, string text)
        {
            var label = Text(text, 13.5, FontWeights.Normal, Color.FromArgb(230, 255, 255, 255));
            label.VerticalAlignment = VerticalAlignment.Center;
            Row.Children.Add(label);
            track = new Border
            {
                Width = 44, Height = 24, CornerRadius = new CornerRadius(12), HorizontalAlignment = HorizontalAlignment.Right,
                VerticalAlignment = VerticalAlignment.Center, BorderThickness = new Thickness(1),
                BorderBrush = new SolidColorBrush(Color.FromArgb(60, 255, 255, 255))
            };
            knob = new Border
            {
                Width = 18, Height = 18, CornerRadius = new CornerRadius(9), Background = Brushes.White,
                HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(2, 0, 0, 0), RenderTransform = slide
            };
            knob.Effect = new DropShadowEffect { BlurRadius = 6, ShadowDepth = 1, Opacity = 0.35 };
            track.Child = knob;
            Row.Children.Add(track);
            Row.MouseLeftButtonDown += delegate (object s, MouseButtonEventArgs e) { e.Handled = true; };
            Row.MouseLeftButtonUp += delegate (object s, MouseButtonEventArgs e) { e.Handled = true; On = !On; Draw(owner, true); };
            Draw(owner, false);
        }

        void Draw(SetupWindow owner, bool animate)
        {
            track.Background = On ? (Brush)owner.accentBrush : new SolidColorBrush(Color.FromArgb(40, 255, 255, 255));
            knob.Background = On ? (Brush)owner.onAccentBrush : Brushes.White;
            // The window is right-to-left: "on" sits at the far (left) end.
            double to = On ? 20 : 0;
            if (!animate) { slide.X = to; return; }
            slide.BeginAnimation(TranslateTransform.XProperty,
                new DoubleAnimation(to, new Duration(TimeSpan.FromMilliseconds(260))) { EasingFunction = new BackEase { Amplitude = 0.4, EasingMode = EasingMode.EaseOut } });
        }
    }
}
