import {HashRouter, Routes, Route, Link} from 'react-router-dom';

function Hello() {
    return <h1>Hello, world!</h1>;
}

function About() {
    return <h1>About this app</h1>;
}

export default function App() {
    return (
        <HashRouter>
            <nav>
                <Link to="/">Home</Link> | <Link to="/about">About</Link>
            </nav>
            <Routes>
                <Route path="/" element={<Hello />} />
                <Route path="/about" element={<About />} />
            </Routes>
        </HashRouter>
    );
}
