import React from 'react';

export default function KeyboardShortcutRow({keys, description}) {
    return (
        <tr>
            <th>
                {keys.map((key, i) => (
                    <React.Fragment key={i}>
                        {key.wrap ? <kbd>{key.text}</kbd> : key.text}
                        {i < keys.length - 1 && ', '}
                    </React.Fragment>
                ))}
            </th>
            <td>{description}</td>
        </tr>
    );
}
